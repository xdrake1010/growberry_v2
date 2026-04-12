import os
import json
import logging
from datetime import datetime

# Base directory for the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Data files
PLANTS_CONFIG_FILE = os.path.join(BASE_DIR, "plants_config.json")
STATS_FILE = os.path.join(BASE_DIR, "statistics.json")

# Timelapse directory - Prefer environment variable or default to project folder/data/timelapse
TIMELAPSE_BASE_DIR = os.environ.get("GROWBERRY_DATA_DIR", os.path.join(BASE_DIR, "data", "timelapse"))

# GPIO Configuration
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

def setup_logging():
    """Configures logging to output to stdout for systemd capture."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )

def load_plants_config():
    if not os.path.exists(PLANTS_CONFIG_FILE):
        return {}
    try:
        with open(PLANTS_CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return {}

def save_plants_config(config_dict):
    try:
        with open(PLANTS_CONFIG_FILE, 'w') as f:
            json.dump(config_dict, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving config: {e}")
