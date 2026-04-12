import time
import schedule
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger("Growberry.Scheduler")

class ScheduleManager:
    def __init__(self, led_controller, tank_controller, irrigation_controller, config_data):
        self.led_controller = led_controller
        self.tank_controller = tank_controller
        self.irrigation_controller = irrigation_controller
        
        # Robust loading
        self.active_cosecha = config_data.get("active_cosecha", "default")
        plants = config_data.get("plants", {})
        
        # If active_cosecha not found, pick first available or empty
        if self.active_cosecha not in plants:
            if plants:
                self.active_cosecha = list(plants.keys())[0]
                logger.warning(f"Active cosecha not found, defaulting to: {self.active_cosecha}")
            else:
                self.active_cosecha = "default"
        
        self.plant_data = plants.get(self.active_cosecha, {}) 
        self.start_date_str = self.plant_data.get("start_date", datetime.now().strftime("%Y-%m-%d"))
        try:
            self.start_date = datetime.strptime(self.start_date_str, "%Y-%m-%d")
        except:
            self.start_date = datetime.now()
            
        self.cycles = self.plant_data.get("cycles", {})

    def apply_cycle_schedule(self, cycle: dict) -> None:
        """
        Applies a lighting and irrigation schedule based on the cycle config.
        Supports 'vegetation' and 'blooming' profiles.
        """
        initial_time = cycle.get("initial_time", 8)
        total_hours = cycle.get("total_hours", 12)
        profile = cycle.get("logic_profile", "vegetation")
        step_mins = cycle.get("sunrise_step_mins", 15)
        
        # Irrigation
        watering_days = cycle.get("watering_days", list(range(7)))
        irrigation_start = cycle.get("irrigation_start_time", "08:00")
        irrigation_timer = cycle.get("irrigation_timer", 15)
        multiplier = cycle.get("multiplier", 1)
        
        # Tank
        tank_time = cycle.get("tank_time", 15)

        schedule.clear()
        
        # --- Lighting Logic ---
        # Start Time (T=0)
        start_dt = datetime.strptime(f"{initial_time:02d}:00", "%H:%M")
        
        # Sequential timestamps
        t0 = start_dt.strftime("%H:%M")
        t1 = (start_dt + timedelta(minutes=step_mins)).strftime("%H:%M")
        t2 = (start_dt + timedelta(minutes=step_mins*2)).strftime("%H:%M")
        
        # Total duration ends at T_start + total_hours
        end_dt = start_dt + timedelta(hours=total_hours)
        
        # End sequence timestamps
        e0 = (end_dt - timedelta(minutes=step_mins*2)).strftime("%H:%M")
        e1 = (end_dt - timedelta(minutes=step_mins)).strftime("%H:%M")
        e2 = end_dt.strftime("%H:%M")

        if profile == "vegetation":
            # Sunrise: Red -> Blue -> Main (Overlap with Red)
            schedule.every().day.at(t0).do(self.led_controller.led_controls["infrared_on"])
            schedule.every().day.at(t1).do(self.led_controller.led_controls["ultrablue_on"])
            
            def main_on_with_overlap():
                self.led_controller.led_controls["main_on"]()
                time.sleep(1) # 1s overlap
                self.led_controller.led_controls["infrared_off"]()
            
            schedule.every().day.at(t2).do(main_on_with_overlap)
            
            # Sunset: Main OFF (Red ON) -> Blue OFF -> Red OFF
            def main_off_with_overlap():
                self.led_controller.led_controls["infrared_on"]()
                time.sleep(1) # 1s overlap
                self.led_controller.led_controls["main_off"]()
                
            schedule.every().day.at(e0).do(main_off_with_overlap)
            schedule.every().day.at(e1).do(self.led_controller.led_controls["ultrablue_off"])
            schedule.every().day.at(e2).do(self.led_controller.led_controls["infrared_off"])

        else: # Blooming Profile
            # Sunrise: Red -> Main (Both stay ON)
            schedule.every().day.at(t0).do(self.led_controller.led_controls["infrared_on"])
            schedule.every().day.at(t1).do(self.led_controller.led_controls["main_on"])
            
            # Sunset: Main OFF -> Red OFF
            schedule.every().day.at(e1).do(self.led_controller.led_controls["main_off"])
            schedule.every().day.at(e2).do(self.led_controller.led_controls["infrared_off"])
            
            # Ensure Blue is OFF in Blooming
            schedule.every().day.at(t0).do(self.led_controller.led_controls["ultrablue_off"])

        # --- Tank Setup ---
        schedule.every().day.at(f"{tank_time:02d}:00").do(self.tank_controller.control_tank)

        # --- Irrigation Execution ---
        def conditional_irrigation():
            today = datetime.now().weekday()
            if today in watering_days:
                logger.info("Triggering scheduled irrigation...")
                self.irrigation_controller.control_irrigation(irrigation_timer=irrigation_timer, multiplier=multiplier)

        schedule.every().day.at(irrigation_start).do(conditional_irrigation)
        
        # Immediate sync
        self.sync_hardware_to_schedule(cycle)

    def is_time_in_range(self, start_h, start_m, end_h, end_m, cur_dt):
        now_total = cur_dt.hour * 60 + cur_dt.minute
        start_total = start_h * 60 + start_m
        end_total = end_h * 60 + end_m
        
        if start_total <= end_total:
            return start_total <= now_total < end_total
        else: # Spans midnight
            return now_total >= start_total or now_total < end_total

    def sync_hardware_to_schedule(self, cycle: dict) -> None:
        """Determines what should be ON/OFF right now and applies it."""
        now = datetime.now()
        cur_h, cur_m = now.hour, now.minute
        
        initial_time = cycle.get("initial_time", 8)
        total_hours = cycle.get("total_hours", 12)
        profile = cycle.get("logic_profile", "vegetation")
        step_mins = cycle.get("sunrise_step_mins", 15)

        start_dt = datetime.strptime(f"{initial_time:02d}:00", "%H:%M")
        end_dt = start_dt + timedelta(hours=total_hours)

        # Step durations in minutes from start
        steps = {
            "t0": 0,
            "t1": step_mins,
            "t2": step_mins * 2,
            "e0": (total_hours * 60) - (step_mins * 2),
            "e1": (total_hours * 60) - step_mins,
            "e2": total_hours * 60
        }

        def get_time_at_step(step_name):
            dt = start_dt + timedelta(minutes=steps[step_name])
            return dt.hour, dt.minute

        # Current state determination
        should_red = False
        should_blue = False
        should_main = False

        if profile == "vegetation":
            # Red: ON [t0-t2] and [e0-e2]
            if self.is_time_in_range(*get_time_at_step("t0"), *get_time_at_step("t2"), now) or \
               self.is_time_in_range(*get_time_at_step("e0"), *get_time_at_step("e2"), now):
                should_red = True
            
            # Blue: ON [t1-e1]
            if self.is_time_in_range(*get_time_at_step("t1"), *get_time_at_step("e1"), now):
                should_blue = True
                
            # Main: ON [t2-e0]
            if self.is_time_in_range(*get_time_at_step("t2"), *get_time_at_step("e0"), now):
                should_main = True
        else:
            # Blooming
            # Red: ON [t0-e2]
            if self.is_time_in_range(*get_time_at_step("t0"), *get_time_at_step("e2"), now):
                should_red = True
            
            # Main: ON [t1-e1]
            if self.is_time_in_range(*get_time_at_step("t1"), *get_time_at_step("e1"), now):
                should_main = True
            
            should_blue = False

        # Apply states
        if should_red: self.led_controller.led_controls["infrared_on"]()
        else: self.led_controller.led_controls["infrared_off"]()
        
        if should_blue: self.led_controller.led_controls["ultrablue_on"]()
        else: self.led_controller.led_controls["ultrablue_off"]()
        
        if should_main: self.led_controller.led_controls["main_on"]()
        else: self.led_controller.led_controls["main_off"]()

    def determine_current_cycle(self) -> Dict[str, Any]:
        """Calculates current cycle phase based on the start date."""
        current_date = datetime.now()
        
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
