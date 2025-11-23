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

# --- Fungsi Verifikasi ---

def verifikasi_switch(name, running_config):
    """Verifikasi keberadaan/ketiadaan VLAN spesifik pada Switch."""
    has_vlan = TARGET_VLAN in running_config

    print(f"  [INFO] Mencari {TARGET_VLAN}...")

    # Switch yang HARUS memiliki VLAN 50
    if name in ["S1", "S2", "S3"]:
        if has_vlan:
            print(f"  [OK] **VLAN 50 ADA** (sesuai ekspektasi)")
        else:
            print(f"  [ERROR] **VLAN 50 TIDAK DITEMUKAN** padahal seharusnya ADA.")

    # Switch yang HARUS kehilangan VLAN 50 (setelah rollback)
    elif name in ["S4", "S5", "S6"]:
        if not has_vlan:
            print(f"  [OK] **VLAN 50 HILANG** (rollback berhasil)")
        else:
            print(f"  [ERROR] **VLAN 50 MASIH ADA** padahal seharusnya dihapus.")
    
    else:
        print(f"  [PERINGATAN] Perangkat Switch {name} tidak memiliki aturan verifikasi spesifik.")

def verifikasi_router(name, interfaces):
    """Verifikasi status Loopback spesifik pada Router."""
    print(f"  [INFO] Mencari interface {TARGET_LOOPBACK}...")
    loop = interfaces.get(TARGET_LOOPBACK)

    if loop:
        # Loopback ditemukan, cek status 'is_up'
        if loop.get("is_up", False):
            print("  [OK] **Loopback1 AKTIF**")
        else:
            print("  [ERROR] Loopback1 ditemukan tetapi **TIDAK AKTIF**")
    else:
        print("  [ERROR] **Loopback1 TIDAK DITEMUKAN** pada router")

def proses_verifikasi(dev):
    """Mengelola koneksi ke perangkat dan memanggil fungsi verifikasi."""
    name = dev.get("name")
    host = dev.get("host")
    user = dev.get("username")
    pwd = dev.get("password")
    enable = dev.get("enable_password")
    driver_name = dev.get("driver")

    print(f"\n--- Verifikasi {name} ({host}) ---")
    
    # 1. Inisialisasi Driver
    try:
        driver = get_network_driver(driver_name)
    except Exception as e:
        print(f"[FATAL] Gagal mendapatkan driver {driver_name}: {e}")
        return

    # 2. Koneksi ke Perangkat
    device = None
    try:
        device = driver(
            hostname=host,
            username=user,
            password=pwd,
            optional_args={"secret": enable, "inline_transfer": True}
        )
        device.open()
    except (ConnectionException, ConnectAuthError) as e:
        # Menangkap error koneksi dan autentikasi spesifik NAPALM
        print(f"[GAGAL] Gagal konek: {e.__class__.__name__} - {e}")
        return
    except Exception as e:
        print(f"[GAGAL] Gagal konek: Kesalahan tidak terduga - {e}")
        return

    # 3. Ambil Konfigurasi dan Interface
    running_config = ""
    interfaces = {}
    
    try:
        # Ambil RUNNING-CONFIG
        running_config = device.get_config().get("running", "")
    except Exception as e:
        print(f"[GAGAL] Gagal membaca running config: {e}")
        device.close()
        return

    # Ambil INTERFACE INFO (hanya jika Router)
    if name.upper().startswith("R"):
        try:
            interfaces = device.get_interfaces()
        except Exception as e:
            print(f"[PERINGATAN] Gagal membaca interfaces: {e}")
            interfaces = {} # Tetap lanjutkan dengan interfaces kosong

    # 4. Verifikasi berdasarkan Tipe Perangkat
    if name.upper().startswith("S"):
        verifikasi_switch(name, running_config)
    elif name.upper().startswith("R"):
        verifikasi_router(name, interfaces)
    else:
        print(f"  [PERINGATAN] Tipe perangkat ({name}) tidak dikenali untuk verifikasi.")

    # 5. Tutup Koneksi
    try:
        device.close()
    except Exception as e:
        print(f"[PERINGATAN] Gagal menutup koneksi: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    devices = load_devices_from_yaml()

    print("\n=== MEMULAI VERIFIKASI PERANGKAT ===\n")

    for dev in devices:
        proses_verifikasi(dev)

    print("\n=== SELESAI VERIFIKASI ===\n")
