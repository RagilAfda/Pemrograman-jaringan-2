import os
import yaml
from napalm import get_network_driver

# Load file devices.yaml
with open("devices.yaml") as f:
    devices = yaml.safe_load(f)

# Membuat folder backup jika belum ada
if not os.path.exists("backup"):
    os.makedirs("backup")

for dev in devices:
    name = dev["name"]
    host = dev["host"]
    user = dev["username"]
    pwd = dev["password"]
    enable = dev["enable_password"]
    driver_name = dev["driver"]

    driver = get_network_driver(driver_name)
    device = driver(
        hostname=host,
        username=user,
        password=pwd,
        optional_args={"secret": enable}
    )

    print(f"Backup {name} di {host}...")

    device.open()
    cfg = device.get_config()["running"]

    with open(f"backup/{name}_pre.cfg","w") as f:
        f.write(cfg)

    device.close()

print("Backup selesai. File tersimpan di folder backup.")
