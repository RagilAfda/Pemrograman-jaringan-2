import yaml
import sys
from napalm import get_network_driver
from napalm.base.exceptions import ConnectionException, ConnectAuthError

# --- Definisi Global ---
TARGET_VLAN = "vlan 50"
TARGET_LOOPBACK = "Loopback1"

def load_devices_from_yaml(filename="devices.yaml"):
    """Memuat daftar perangkat dari file YAML."""
    try:
        with open(filename, 'r') as f:
            devices = yaml.safe_load(f)
        if not devices:
            print("[ERROR] File devices.yaml kosong atau tidak valid.")
            sys.exit(1)
        return devices
    except FileNotFoundError:
        print(f"[FATAL] Gagal membaca {filename}: File tidak ditemukan.")
        sys.exit(1)
    except Exception as e:
        print(f"[FATAL] Gagal membaca {filename}: {e}")
        sys.exit(1)

# ============================================================
#            FUNGSI VERIFIKASI SWITCH (UPDATED)
# ============================================================
def verifikasi_switch(name, running_config):
    """Verifikasi VLAN 50 pada switch S1–S6.

       Jika ada → ADA
       Jika tidak → HILANG
    """
    print(f"  [INFO] Mencari {TARGET_VLAN}...")

    has_vlan = TARGET_VLAN in running_config

    if has_vlan:
        print(f"  [OK] VLAN **ADA** pada {name}")
    else:
        print(f"  [OK] VLAN **HILANG** pada {name}")

# ============================================================
#                FUNGSI VERIFIKASI ROUTER
# ============================================================
def verifikasi_router(name, interfaces):
    """Verifikasi status Loopback pada Router."""
    print(f"  [INFO] Mencari interface {TARGET_LOOPBACK}...")

    loop = interfaces.get(TARGET_LOOPBACK)

    if loop:
        if loop.get("is_up", False):
            print("  [OK] **Loopback AKTIF**")
        else:
            print("  [ERROR] Loopback ditemukan tetapi **TIDAK AKTIF**")
    else:
        print("  [ERROR] **Loopback TIDAK DITEMUKAN** pada router")

# ============================================================
#               MAIN VERIFICATION PROCESS
# ============================================================
def proses_verifikasi(dev):
    """Koneksi ke perangkat & menjalankan verifikasi."""
    name = dev.get("name")
    host = dev.get("host")
    user = dev.get("username")
    pwd = dev.get("password")
    enable = dev.get("enable_password")
    driver_name = dev.get("driver")

    print(f"\n--- Verifikasi {name} ({host}) ---")

    # Inisialisasi driver
    try:
        driver = get_network_driver(driver_name)
    except Exception as e:
        print(f"[FATAL] Driver error ({driver_name}): {e}")
        return

    # Koneksi
    try:
        device = driver(
            hostname=host,
            username=user,
            password=pwd,
            optional_args={"secret": enable, "inline_transfer": True}
        )
        device.open()
    except (ConnectionException, ConnectAuthError) as e:
        print(f"[GAGAL] Gagal konek ({e.__class__.__name__}): {e}")
        return
    except Exception as e:
        print(f"[GAGAL] Error koneksi: {e}")
        return

    # Ambil running config
    try:
        running_config = device.get_config().get("running", "")
    except Exception as e:
        print(f"[GAGAL] Gagal membaca running config: {e}")
        device.close()
        return

    # Ambil interface info (khusus router)
    interfaces = {}
    if name.startswith("R"):
        try:
            interfaces = device.get_interfaces()
        except Exception as e:
            print(f"[PERINGATAN] Gagal membaca interfaces: {e}")

    # Mulai verifikasi
    if name.startswith("S"):
        verifikasi_switch(name, running_config)
    elif name.startswith("R"):
        verifikasi_router(name, interfaces)
    else:
        print(f"[PERINGATAN] Perangkat {name} tidak dikenali.")

    # Tutup koneksi
    try:
        device.close()
    except:
        pass

# ============================================================
#                          MAIN
# ============================================================
if __name__ == "__main__":
    devices = load_devices_from_yaml()

    print("\n=== MEMULAI VERIFIKASI PERANGKAT ===\n")

    for dev in devices:
        proses_verifikasi(dev)

    print("\n=== SELESAI VERIFIKASI ===\n")
