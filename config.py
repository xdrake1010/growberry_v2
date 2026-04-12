import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLANTS_CONFIG_FILE = os.path.join(BASE_DIR, "plants_config.json")
STATS_FILE = os.path.join(BASE_DIR, "statistics.json")

# Path based on user request for the raspberry
# Make sure this has right permissions or the user `xdrake` can write to it.
TIMELAPSE_BASE_DIR = "/home/growberry/timelapse"

# If the folder doesn't exist, we will create it automatically in the camera_controller
GPIO_PINS = {
    "dht11_sensor": 16,
    "tank_sensor": 24,
    "water_flow_sensor": 23,
    "main_led": 9,
    "infrared_led": 19,
    "ultrablue_led": 17,
    "ventilation": 27,
    "irrigation": 11,
    "tank_charge": 5
}

def load_plants_config():
    if not os.path.exists(PLANTS_CONFIG_FILE):
        return {}
    with open(PLANTS_CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_plants_config(config_dict):
    with open(PLANTS_CONFIG_FILE, 'w') as f:
        json.dump(config_dict, f, indent=4)
