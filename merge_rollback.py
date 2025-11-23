import os
import yaml
from napalm import get_network_driver
import sys

# --- Variabel Global ---
ROLLBACK_FILE = "rollback_vlan.cfg"
TARGET_SWITCHES = ["S4", "S5", "S6"]

# --- Load Daftar Device ---
try:
    with open("devices.yaml") as f:
        devices = yaml.safe_load(f)
    print("Berhasil membaca devices.yaml.")
except Exception as e:
    print(f"Gagal membaca devices.yaml: {e}")
    sys.exit(1)

# --- Logika Utama Rollback Merge ---

print("\n=== MULAI PROSES ROLLBACK MERGE PARSIAL (NAPALM) ===")

for dev in devices:
    # Ambil detail perangkat
    name = dev.get("name")
    host = dev.get("host")
    user = dev.get("username")
    pwd = dev.get("password")
    enable = dev.get("enable_password")
    driver_name = dev.get("driver")

    # Filter: Proses hanya S4, S5, S6
    if name not in TARGET_SWITCHES:
        continue

    # Validasi data perangkat
    if not all([name, host, user, pwd, enable, driver_name]):
        print(f"\n--- Data device {name} tidak lengkap. Lewati. ---")
        continue

    print(f"\n=== Merge Rollback Processing: {name} ({host}) ===")

    driver = get_network_driver(driver_name)

    # 1. Koneksi NAPALM
    try:
        device = driver(
            hostname=host,
            username=user,
            password=pwd,
            optional_args={"secret": enable, "inline_transfer": True}
        )
        device.open()
        print(f"  [NAPALM] Koneksi berhasil.")
    except Exception as e:
        print(f"  [NAPALM] Gagal konek: {e}")
        continue

    # 2. Load rollback merge candidate
    try:
        # load_merge_candidate hanya menerapkan baris konfigurasi yang ada di file.
        # Ini memungkinkan rollback parsial (misalnya, menghapus VLAN tertentu).
        device.load_merge_candidate(filename=ROLLBACK_FILE)
        print(f"  [NAPALM] Berhasil load {ROLLBACK_FILE} sebagai merge candidate.")
    except Exception as e:
        print(f"  [NAPALM] Gagal load_merge_candidate: {e}")
        device.close()
        continue

    # 3. Cek diff
    try:
        diff = device.compare_config()
    except Exception as e:
        print(f"  [NAPALM] Gagal compare_config: {e}")
        device.discard_config()
        device.close()
        continue

    print(f"\n  Diff untuk {name}:")
    print(diff if diff else "  Tidak ada perubahan pada switch ini.")

    if not diff:
        print("  Tidak ada konfigurasi yang perlu di-rollback. Discard.")
        device.discard_config()
        device.close()
        continue

    # 4. Tanya commit
    choice = input(f"  Commit rollback merge pada {name}? (y/n): ").strip().lower()

    if choice == "y":
        try:
            device.commit_config()
            print("  [NAPALM] Rollback merge berhasil di-commit untuk", name)
        except Exception as e:
            print(f"  [NAPALM] Commit gagal: {e}")
            try:
                device.discard_config()
                print("  [NAPALM] Rollback dibatalkan/discard setelah commit gagal.")
            except:
                pass
    else:
        print("  [NAPALM] Rollback dibatalkan. discard_config() dijalankan.")
        try:
            device.discard_config()
        except:
            pass

    device.close()

print("\n=== PROSES ROLLBACK MERGE PARSIAL SELESAI ===")
