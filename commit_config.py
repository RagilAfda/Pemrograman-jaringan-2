import os
import yaml
from napalm import get_network_driver
from netmiko import ConnectHandler
import difflib
import sys

# --- Variabel Global ---
SWITCH_CHANGESET = "vlan.cfg"
ROUTER_CHANGESET = "loopback.cfg"
BACKUP_DIR = "backup"

# --- Persiapan Awal ---
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
    print(f"Direktori '{BACKUP_DIR}' dibuat.")

try:
    with open("devices.yaml") as f:
        devices = yaml.safe_load(f)
    print("Berhasil membaca devices.yaml.")
except Exception as e:
    print(f"Gagal membaca devices.yaml: {e}")
    sys.exit(1)

# --- Fungsi Pembantu ---

def save_backup(name, content, suffix):
    """Menyimpan konfigurasi ke direktori backup."""
    path = os.path.join(BACKUP_DIR, f"{name}_{suffix}.cfg")
    with open(path, "w") as f:
        f.write(content)
    print(f"  Saved: {path}")

def show_text_diff(a, b, a_label="before", b_label="after"):
    """Menampilkan perbedaan teks menggunakan difflib.unified_diff."""
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile=a_label, tofile=b_label, lineterm="")
    diff_text = "".join(diff)
    if not diff_text:
        print("Tidak ada perubahan.")
    else:
        print(diff_text)

# --- Logika Utama ---

print("\n=== MULAI PROSES KONFIGURASI JARINGAN ===")

for dev in devices:
    # Ambil detail perangkat
    name = dev.get("name")
    host = dev.get("host")
    user = dev.get("username")
    pwd = dev.get("password")
    enable = dev.get("enable_password")
    driver_name = dev.get("driver")

    # Validasi data perangkat
    if not all([name, host, user, pwd, enable, driver_name]):
        print(f"\n--- Data device {name} tidak lengkap. Lewati. ---")
        continue

    # Tentukan tipe perangkat: Router jika nama diawali 'R'
    is_router = name.upper().startswith("R")

    print(f"\n--- Memproses {name} ({host}) ---")

    # --- Logika untuk ROUTER (menggunakan Netmiko) ---
    if is_router:
        netmiko_device = {
            "device_type": "cisco_ios",
            "host": host,
            "username": user,
            "password": pwd,
            "secret": enable,
        }

        try:
            # Koneksi Netmiko
            conn = ConnectHandler(**netmiko_device)
            conn.enable()
            print("  [Netmiko] Koneksi berhasil.")
            running_pre = conn.send_command("show running-config")
            save_backup(name, running_pre, "pre")
        except Exception as e:
            print(f"  [Netmiko] Gagal konek router: {e}")
            continue

        try:
            # Baca changeset router
            with open(ROUTER_CHANGESET) as f:
                # Filter baris kosong/whitespace
                candidate_lines = [ln.strip() for ln in f if ln.strip()]
        except Exception as e:
            print(f"  [Netmiko] Gagal membaca {ROUTER_CHANGESET}: {e}")
            conn.disconnect()
            continue

        print(f"\n  Planned commands for {name} (dari {ROUTER_CHANGESET}):")
        for c in candidate_lines:
            print(f"    {c}")
        print()

        # Tampilkan diff (meski tidak selalu akurat untuk Netmiko karena tidak ada fungsi 'merge')
        # Di sini hanya membandingkan config yang sudah ada vs isi file perubahan
        planned_text = "\n".join(candidate_lines) + "\n"
        # show_text_diff(running_pre, planned_text, "running", "candidate") # Netmiko tidak punya fungsi compare built-in seperti NAPALM

        choice = input(f"  Commit konfigurasi untuk {name}? (y/n): ").strip().lower()
        if choice == "y":
            try:
                # Commit konfigurasi
                output = conn.send_config_set(candidate_lines)
                print("  [Netmiko] Output Command:")
                print(output)
                # Ambil config pasca-commit
                running_post = conn.send_command("show running-config")
                save_backup(name, running_post, "post")
            except Exception as e:
                print(f"  [Netmiko] Gagal commit router: {e}")
            finally:
                conn.disconnect()
        else:
            print(f"  Discard pada {name}")
            conn.disconnect()

    # --- Logika untuk SWITCH (menggunakan NAPALM) ---
    else:
        # Dapatkan driver NAPALM
        driver = get_network_driver(driver_name)

        try:
            # Koneksi NAPALM
            device = driver(
                hostname=host,
                username=user,
                password=pwd,
                optional_args={"secret": enable, "inline_transfer": True}
            )
            device.open()
            print(f"  [NAPALM] Koneksi berhasil dengan driver {driver_name}.")
        except Exception as e:
            print(f"  [NAPALM] Gagal konek: {e}")
            continue

        try:
            # Ambil running-config sebelum load candidate
            running_pre = device.get_config().get("running", "")
            save_backup(name, running_pre, "pre")
        except Exception as e:
            print(f"  [NAPALM] Gagal ambil running-config: {e}")
            device.close()
            continue

        try:
            # Load candidate config
            device.load_merge_candidate(filename=SWITCH_CHANGESET)
        except Exception as e:
            print(f"  [NAPALM] Gagal load merge dari {SWITCH_CHANGESET}: {e}")
            device.close()
            continue

        try:
            # Bandingkan konfigurasi
            diff = device.compare_config()
        except Exception as e:
            print(f"  [NAPALM] Gagal compare config: {e}")
            device.discard_config()
            device.close()
            continue

        print(f"\n  Diff untuk {name}:")
        print(diff if diff else "  Tidak ada perubahan.")

        if not diff:
            # Jika tidak ada perbedaan, batalkan dan tutup koneksi
            device.discard_config()
            device.close()
            continue

        choice = input(f"  Commit konfigurasi untuk {name}? (y/n): ").strip().lower()
        if choice == "y":
            try:
                # Commit konfigurasi
                device.commit_config()
                print("  [NAPALM] Commit berhasil.")
                # Ambil config pasca-commit
                running_post = device.get_config().get("running", "")
                save_backup(name, running_post, "post")
            except Exception as e:
                print(f"  [NAPALM] Gagal commit: {e}")
                try:
                    # Coba discard config jika commit gagal
                    device.discard_config()
                    print("  [NAPALM] Percobaan discard config setelah commit gagal.")
                except:
                    pass
        else:
            # Batalkan konfigurasi
            print(f"  Discard pada {name}")
            try:
                device.discard_config()
                print("  [NAPALM] Discard config berhasil.")
            except:
                pass

        # Tutup koneksi NAPALM
        device.close()


print("\n=== SELESAI ===")
