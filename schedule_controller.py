import time
import schedule
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class ScheduleManager:
    def __init__(self, led_controller, tank_controller, irrigation_controller, config_data):
        self.led_controller = led_controller
        self.tank_controller = tank_controller
        self.irrigation_controller = irrigation_controller
        
        self.active_cosecha = config_data.get("active_cosecha", "default")
        self.plant_data = config_data.get("plants", {}).get("default", {}) # We default to standard if not found
        
        self.start_date_str = self.plant_data.get("start_date", datetime.now().strftime("%Y-%m-%d"))
        self.start_date = datetime.strptime(self.start_date_str, "%Y-%m-%d")
        
        self.cycles = self.plant_data.get("cycles", {})

    def apply_cycle_schedule(self, cycle: dict) -> None:
        initial_time = cycle.get("initial_time", 8)
        total_hours = cycle.get("total_hours", 12)
        main_delay = cycle.get("main_delay", 30)
        ultrablue_delay = cycle.get("ultrablue_delay", 15)
        infrared_delay = cycle.get("infrared_delay", 15)
        tank_time = cycle.get("tank_time", 15)
        watering_days = cycle.get("watering_days", list(range(7)))
        multiplier = cycle.get("multiplier", 1)
        irrigation_time = cycle.get("irrigation_time", 15)
        irrigation_timer = cycle.get("irrigation_timer", 15)
        extra_red = cycle.get("extra_red", False)

        off_time = (initial_time + total_hours) % 24
        schedule.clear()

        # Infrared LED
        schedule.every().day.at(f'{initial_time:02d}:00').do(self.led_controller.led_controls["infrared_on"])
        if not extra_red:
            schedule.every().day.at(f'{initial_time:02d}:{infrared_delay:02d}').do(self.led_controller.led_controls["infrared_off"])
            schedule.every().day.at(f'{(off_time-1)%24:02d}:{60-infrared_delay:02d}').do(self.led_controller.led_controls["infrared_on"])
        schedule.every().day.at(f'{off_time:02d}:00').do(self.led_controller.led_controls["infrared_off"])

        # Ultrablue & Main LEDs
        schedule.every().day.at(f'{(initial_time)%24:02d}:{ultrablue_delay:02d}').do(self.led_controller.led_controls["ultrablue_on"])
        schedule.every().day.at(f'{(initial_time)%24:02d}:{main_delay:02d}').do(self.led_controller.led_controls["main_on"])
        
        schedule.every().day.at(f'{(off_time-1)%24:02d}:{60-main_delay:02d}').do(self.led_controller.led_controls["main_off"])
        schedule.every().day.at(f'{(off_time-1)%24:02d}:{60-ultrablue_delay:02d}').do(self.led_controller.led_controls["ultrablue_off"])

        # Tank Setup
        schedule.every().day.at(f'{tank_time:02d}:00').do(self.tank_controller.control_tank)

        # Irrigation Execution 
        def conditional_irrigation():
            today = datetime.now().weekday()
            if today in watering_days:
                self.irrigation_controller.control_irrigation(irrigation_timer=irrigation_timer, multiplier=multiplier)

        schedule.every().day.at(f'{irrigation_time:02d}:00').do(conditional_irrigation)

    def determine_current_cycle(self) -> Dict[str, Any]:
        """Calculates current cycle phase based on the start date."""
        current_date = datetime.now()
        total_days = (current_date - self.start_date).days
        
        cycle_start = self.start_date
        
        for cycle_name, cycle_config in self.cycles.items():
            duration = cycle_config.get("duration_days", 1)
            cycle_end = cycle_start + timedelta(days=duration)
            
            if cycle_start <= current_date < cycle_end:
                return {
                    "cycle_name": cycle_name,
                    "cycle_config": cycle_config,
                    "start_date": cycle_start,
                    "end_date": cycle_end,
                    "days_elapsed": (current_date - cycle_start).days,
                    "days_remaining": (cycle_end - current_date).days
                }
            cycle_start = cycle_end
            
        return {} # Done or not started yet

    def refresh_schedule(self):
        """Re-evaluate the date and re-aply the schedule routing."""
        info = self.determine_current_cycle()
        if info:
            self.apply_cycle_schedule(info["cycle_config"])
            return info
        return None

    def get_cycle_info(self) -> Dict[str, Any]:
        info = self.determine_current_cycle()
        if not info:
             return {"status": "inactive", "total_days": (datetime.now() - self.start_date).days}
             
        res = {
             "status": "active",
             "total_days": (datetime.now() - self.start_date).days,
             "current_cycle": info["cycle_name"],
             "days_elapsed": info["days_elapsed"],
             "days_remaining": info["days_remaining"],
             "cycle_start_date": info["start_date"].isoformat(),
             "cycle_end_date": info["end_date"].isoformat(),
             "schedule": info["cycle_config"]
        }
        return res
