import os
import yaml
from napalm import get_network_driver
from netmiko import ConnectHandler
import difflib
import sys

# --- Variabel Global ---
BACKUP_FOLDER = "backup"

# --- Load Daftar Device ---
try:
    with open("devices.yaml") as f:
        devices = yaml.safe_load(f)
    print("Berhasil membaca devices.yaml.")
except Exception as e:
    print(f"Gagal baca devices.yaml: {e}")
    sys.exit(1)

# --- Fungsi Pembantu ---

def show_text_diff(a, b, a_label="before", b_label="after"):
    """Menampilkan perbedaan teks menggunakan difflib.unified_diff."""
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile=a_label, tofile=b_label, lineterm="")
    diff_text = "".join(diff)
    if not diff_text:
        print("  Tidak ada perubahan.")
    else:
        print(diff_text)

# --- Logika Utama Rollback Simulation ---

print("\n=== MULAI SIMULASI ROLLBACK JARINGAN ===")

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

    print(f"\n=== Rollback Simulation: {name} ({host}) ===")

    # Tentukan path file backup lama (_pre.cfg)
    backup_file = os.path.join(BACKUP_FOLDER, f"{name}_pre.cfg")

    if not os.path.exists(backup_file):
        print(f"  [Error] Backup lama tidak ditemukan: {backup_file}")
        continue

    # --- Router: Netmiko (Simulasi Manual Diff) ---
    if name.upper().startswith("R"):
        print("  [Router] Perangkat terdeteksi. Rollback disimulasikan manual dengan Netmiko.")

        try:
            # 1. Koneksi Netmiko
            conn = ConnectHandler(
                device_type="cisco_ios",
                host=host,
                username=user,
                password=pwd,
                secret=enable
            )
            conn.enable()
            print("  [Netmiko] Koneksi berhasil.")
        except Exception as e:
            print(f"  [Netmiko] Gagal konek router: {e}")
            continue

        try:
            # 2. Ambil Running Config saat ini
            current_run = conn.send_command("show running-config")
            conn.disconnect()
        except Exception as e:
            print(f"  [Netmiko] Gagal ambil running config router: {e}")
            conn.disconnect()
            continue

        try:
            # 3. Baca konten Backup
            with open(backup_file) as f:
                backup_text = f.read()
        except Exception as e:
            print(f"  [Netmiko] Gagal baca backup: {e}")
            continue

        # 4. Tampilkan Diff (Running NOW vs Backup PRE)
        print("\n  Diff (Running Config saat ini vs Konfigurasi Rollback Target):")
        show_text_diff(current_run, backup_text, "current", "backup_pre")

        print("\n  [INFO] Rollback hanya simulasi. Tidak ada perubahan diterapkan pada router.")

    # --- Switch: NAPALM (load_replace_candidate) ---
    else:
        # 1. Inisialisasi dan Koneksi NAPALM
        driver = get_network_driver(driver_name)

        try:
            device = driver(
                hostname=host,
                username=user,
                password=pwd,
                optional_args={"secret": enable, "inline_transfer": True}
            )
            device.open()
            print(f"  [NAPALM] Koneksi berhasil dengan driver {driver_name}.")
        except Exception as e:
            print(f"  [NAPALM] Gagal konek switch: {e}")
            continue

        # 2. Load replace candidate
        try:
            # Menginstruksikan perangkat untuk mengganti seluruh konfigurasi dengan isi file backup
            device.load_replace_candidate(filename=backup_file)
            print(f"  [NAPALM] Berhasil load {backup_file} sebagai replace candidate.")
        except Exception as e:
            print(f"  [NAPALM] Gagal load replace candidate: {e}")
            device.close()
            continue

        # 3. Bandingkan konfigurasi (Simulasi Rollback)
        try:
            diff = device.compare_config()
        except Exception as e:
            print(f"  [NAPALM] Error compare_config: {e}")
            device.discard_config()
            device.close()
            continue

        print("\n  Diff untuk", name, "(Running Config -> Rollback Target):")
        print(diff if diff else "  Tidak ada perubahan.")

        # 4. Discard (Simulasi, tidak Commit)
        print("\n  [INFO] Rollback hanya simulasi. discard_config() dijalankan.")
        try:
            device.discard_config()
        except:
            pass

        device.close()

print("\n=== Rollback Simulation Complete ===")
