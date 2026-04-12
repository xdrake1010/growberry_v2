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

def get_default_config():
    """Returns the hardcoded default 'Standard Mix' harvest plan with 4 phases and gradual reduction (List format)."""
    return {
        "active_cosecha": "Standard_Mix",
        "plants": {
            "Standard_Mix": {
                "name": "Standard Mix",
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "cycles": [
                    {
                        "name": "seeding",
                        "duration_days": 3,
                        "initial_time": 8,
                        "total_hours": 23,
                        "target_total_hours": 23,
                        "ultra_red_step_mins": 15,
                        "infra_blue_step_mins": 15,
                        "ultra_red_sunrise": true,
                        "ultra_red_full": false,
                        "infra_blue_sunrise": true,
                        "infra_blue_full": true,
                        "tank_time": 2,
                        "watering_days": [1, 3, 5],
                        "multiplier": 1,
                        "irrigation_start_time": "08:00",
                        "irrigation_timer": 15,
                        "target_volume_liters": 0.0
                    },
                    {
                        "name": "vegetation",
                        "duration_days": 35,
                        "initial_time": 8,
                        "total_hours": 21,
                        "target_total_hours": 21,
                        "ultra_red_step_mins": 15,
                        "infra_blue_step_mins": 15,
                        "ultra_red_sunrise": true,
                        "ultra_red_full": false,
                        "infra_blue_sunrise": true,
                        "infra_blue_full": true,
                        "tank_time": 4,
                        "watering_days": [0, 2, 4, 6],
                        "multiplier": 1,
                        "irrigation_start_time": "08:00",
                        "irrigation_timer": 15,
                        "target_volume_liters": 0.0
                    },
                    {
                        "name": "pre_blooming",
                        "duration_days": 8,
                        "initial_time": 8,
                        "total_hours": 21,
                        "target_total_hours": 13,
                        "ultra_red_step_mins": 15,
                        "infra_blue_step_mins": 15,
                        "ultra_red_sunrise": true,
                        "ultra_red_full": true,
                        "infra_blue_sunrise": false,
                        "infra_blue_full": false,
                        "tank_time": 15,
                        "watering_days": [0, 1, 3, 5, 6],
                        "multiplier": 1,
                        "irrigation_start_time": "08:00",
                        "irrigation_timer": 15,
                        "target_volume_liters": 0.0
                    },
                    {
                        "name": "blooming",
                        "duration_days": 60,
                        "initial_time": 8,
                        "total_hours": 12,
                        "target_total_hours": 12,
                        "ultra_red_step_mins": 15,
                        "infra_blue_step_mins": 15,
                        "ultra_red_sunrise": true,
                        "ultra_red_full": true,
                        "infra_blue_sunrise": false,
                        "infra_blue_full": false,
                        "tank_time": 15,
                        "watering_days": [0, 1, 2, 3, 4, 5, 6],
                        "multiplier": 1,
                        "irrigation_start_time": "08:00",
                        "irrigation_timer": 15,
                        "target_volume_liters": 0.0
                    },
                    {
                        "name": "harvest_time",
                        "duration_days": 1,
                        "initial_time": 8,
                        "total_hours": 0,
                        "target_total_hours": 0,
                        "ultra_red_step_mins": 0,
                        "infra_blue_step_mins": 0,
                        "ultra_red_sunrise": false,
                        "ultra_red_full": false,
                        "infra_blue_sunrise": false,
                        "infra_blue_full": false,
                        "tank_time": 12,
                        "watering_days": [],
                        "multiplier": 0,
                        "irrigation_start_time": "08:00",
                        "irrigation_timer": 0,
                        "target_volume_liters": 0.0
                    }
                ]
            }
        }
    }

def load_plants_config():
    if not os.path.exists(PLANTS_CONFIG_FILE):
        return get_default_config()
    try:
        with open(PLANTS_CONFIG_FILE, 'r') as f:
            data = json.load(f)
            if not data or "plants" not in data or not data["plants"]:
                return get_default_config()
            return data
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return get_default_config()

def save_plants_config(config_dict):
    try:
        with open(PLANTS_CONFIG_FILE, 'w') as f:
            json.dump(config_dict, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving config: {e}")
