import time
import schedule
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger("Growberry.Scheduler")

class ScheduleManager:
    def __init__(self, led_controller, tank_controller, irrigation_controller, config_data, scheduler_lock):
        self.led_controller = led_controller
        self.tank_controller = tank_controller
        self.irrigation_controller = irrigation_controller
        self.scheduler_lock = scheduler_lock
        self.reload_config(config_data)

    def reload_config(self, config_data: dict):
        """Reloads harvest plan and start date from the provided config data."""
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
            logger.error(f"Invalid start date: {self.start_date_str}. Using today.")
            self.start_date = datetime.now()
            
        self.cycles = self.plant_data.get("cycles", [])
        logger.info(f"Schedule reloaded for: {self.active_cosecha} (Started: {self.start_date_str})")

    def apply_cycle_schedule(self, cycle: dict, days_elapsed: int = 0) -> None:
        """
        Applies a lighting and irrigation schedule based on the cycle config.
        Supports independent step durations and gradual light hour transitions.
        """
        initial_time = cycle.get("initial_time", 8)
        start_hours = cycle.get("total_hours", 12)
        target_hours = cycle.get("target_total_hours", None)
        duration_days = cycle.get("duration_days", 1)
        
        # Calculate current hours if gradual transition is enabled
        if target_hours is not None and duration_days > 1:
            progress = min(days_elapsed / (duration_days - 1), 1.0) if duration_days > 1 else 1.0
            total_hours = start_hours + (target_hours - start_hours) * progress
            logger.info(f"Gradual Hours: {start_hours} -> {target_hours} (Day {days_elapsed}/{duration_days}). Current: {total_hours:.2f}h")
        else:
            total_hours = start_hours

        red_step = cycle.get("ultra_red_step_mins", 15)
        blue_step = cycle.get("infra_blue_step_mins", 15)
        
        # Granular Flags
        red_sunrise = cycle.get("ultra_red_sunrise", False)
        red_full = cycle.get("ultra_red_full", False)
        blue_sunrise = cycle.get("infra_blue_sunrise", False)
        blue_full = cycle.get("infra_blue_full", False)
        
        # Irrigation
        watering_days = cycle.get("watering_days", list(range(7)))
        irrigation_start = cycle.get("irrigation_start_time", "08:00")
        irrigation_timer = cycle.get("irrigation_timer", 15)
        multiplier = cycle.get("multiplier", 1)
        
        # Tank
        tank_time = cycle.get("tank_time", 15)

        with self.scheduler_lock:
            # ONLY clear lighting/irrigation tasks, DO NOT touch background logging/timelapse
            schedule.clear('lighting_tasks')
            
            # --- Lighting Logic ---
            start_dt = datetime.strptime(f"{initial_time:02d}:00", "%H:%M")
            t0 = start_dt.strftime("%H:%M")
            t1 = (start_dt + timedelta(minutes=red_step)).strftime("%H:%M")
            t2 = (start_dt + timedelta(minutes=red_step + blue_step)).strftime("%H:%M")
            
            end_dt = start_dt + timedelta(hours=total_hours)
            e0 = (end_dt - timedelta(minutes=red_step + blue_step)).strftime("%H:%M")
            e1 = (end_dt - timedelta(minutes=red_step)).strftime("%H:%M")
            e2 = end_dt.strftime("%H:%M")

            # Start Sequence
            if red_sunrise:
                schedule.every().day.at(t0).do(self.led_controller.led_controls["infrared_on"]).tag('lighting_tasks')
            elif red_full:
                schedule.every().day.at(t2).do(self.led_controller.led_controls["infrared_on"]).tag('lighting_tasks')

            if blue_sunrise:
                schedule.every().day.at(t1).do(self.led_controller.led_controls["ultrablue_on"]).tag('lighting_tasks')
            elif blue_full:
                schedule.every().day.at(t2).do(self.led_controller.led_controls["ultrablue_on"]).tag('lighting_tasks')

            def main_on_with_overlap():
                self.led_controller.led_controls["main_on"]()
                time.sleep(1)
                if red_sunrise and not red_full:
                    self.led_controller.led_controls["infrared_off"]()
                if blue_sunrise and not blue_full:
                    self.led_controller.led_controls["ultrablue_off"]()
            
            schedule.every().day.at(t2).do(main_on_with_overlap).tag('lighting_tasks')
            
            # End Sequence
            def main_off_with_overlap():
                if red_sunrise and not red_full:
                    self.led_controller.led_controls["infrared_on"]()
                if blue_sunrise and not blue_full:
                    self.led_controller.led_controls["ultrablue_on"]()
                time.sleep(1)
                self.led_controller.led_controls["main_off"]()
                if not red_full and not red_sunrise:
                     self.led_controller.led_controls["infrared_off"]()
                if not blue_full and not blue_sunrise:
                     self.led_controller.led_controls["ultrablue_off"]()
                    
            schedule.every().day.at(e0).do(main_off_with_overlap).tag('lighting_tasks')
            
            if blue_sunrise:
                schedule.every().day.at(e1).do(self.led_controller.led_controls["ultrablue_off"]).tag('lighting_tasks')
            elif blue_full:
                schedule.every().day.at(e2).do(self.led_controller.led_controls["ultrablue_off"]).tag('lighting_tasks')

            if red_sunrise or red_full:
                schedule.every().day.at(e2).do(self.led_controller.led_controls["infrared_off"]).tag('lighting_tasks')

            # --- Tank & Irrigation ---
            schedule.every().day.at(f"{tank_time:02d}:00").do(self.tank_controller.control_tank).tag('lighting_tasks')
            def conditional_irrigation():
                today = datetime.now().weekday()
                if today in watering_days:
                    logger.info("Triggering scheduled irrigation...")
                    self.irrigation_controller.control_irrigation(irrigation_timer=irrigation_timer, multiplier=multiplier)
            schedule.every().day.at(irrigation_start).do(conditional_irrigation).tag('lighting_tasks')
        
        self.sync_hardware_to_schedule(cycle, days_elapsed)

    def is_time_in_range(self, start_h, start_m, end_h, end_m, cur_dt):
        now_total = cur_dt.hour * 60 + cur_dt.minute
        start_total = start_h * 60 + start_m
        end_total = end_h * 60 + end_m
        if start_total <= end_total:
            return start_total <= now_total < end_total
        return now_total >= start_total or now_total < end_total

    def sync_hardware_to_schedule(self, cycle: dict, days_elapsed: int = 0) -> None:
        """Determines what should be ON/OFF right now and applies it."""
        now = datetime.now()
        initial_time = cycle.get("initial_time", 8)
        
        start_hours = cycle.get("total_hours", 12)
        target_hours = cycle.get("target_total_hours", None)
        duration_days = cycle.get("duration_days", 1)
        
        if target_hours is not None and duration_days > 1:
            progress = min(days_elapsed / (duration_days - 1), 1.0) if duration_days > 1 else 1.0
            total_hours = start_hours + (target_hours - start_hours) * progress
        else:
            total_hours = start_hours

        red_step = cycle.get("ultra_red_step_mins", 15)
        blue_step = cycle.get("infra_blue_step_mins", 15)
        
        red_sunrise = cycle.get("ultra_red_sunrise", False)
        red_full = cycle.get("ultra_red_full", False)
        blue_sunrise = cycle.get("infra_blue_sunrise", False)
        blue_full = cycle.get("infra_blue_full", False)

        start_dt = datetime.strptime(f"{initial_time:02d}:00", "%H:%M")
        def get_t(m):
            dt = start_dt + timedelta(minutes=m)
            return dt.hour, dt.minute

        t0, t1, t2 = 0, red_step, red_step + blue_step
        e0, e1, e2 = (total_hours * 60) - (red_step + blue_step), (total_hours * 60) - red_step, total_hours * 60

        should_red = False
        should_blue = False
        should_main = self.is_time_in_range(*get_t(t2), *get_t(e0), now)

        # Red Logic
        if red_sunrise and (self.is_time_in_range(*get_t(t0), *get_t(t2), now) or self.is_time_in_range(*get_t(e0), *get_t(e2), now)):
            should_red = True
        if red_full and self.is_time_in_range(*get_t(t2), *get_t(e0), now):
            should_red = True

        # Blue Logic
        if blue_sunrise and (self.is_time_in_range(*get_t(t1), *get_t(t2), now) or self.is_time_in_range(*get_t(e0), *get_t(e1), now)):
            should_blue = True
        if blue_full and self.is_time_in_range(*get_t(t2), *get_t(e0), now):
            should_blue = True

        if should_red: self.led_controller.led_controls["infrared_on"]()
        else: self.led_controller.led_controls["infrared_off"]()
        
        if should_blue: self.led_controller.led_controls["ultrablue_on"]()
        else: self.led_controller.led_controls["ultrablue_off"]()
        
        if should_main: self.led_controller.led_controls["main_on"]()
        else: self.led_controller.led_controls["main_off"]()

    def determine_current_cycle(self) -> Dict[str, Any]:
        """Calculates current cycle phase based on an ordered list of cycles."""
        current_date = datetime.now()
        cycle_start = self.start_date
        
        # self.cycles is now a LIST: [{"name": "seeding", ...}, {"name": "vegetation", ...}]
        cycles_list = self.cycles if isinstance(self.cycles, list) else []
        
        for cycle_config in cycles_list:
            cycle_name = cycle_config.get("name", "unknown")
            duration = cycle_config.get("duration_days", 1)
            cycle_end = cycle_start + timedelta(days=duration)
            
            if cycle_start <= current_date < cycle_end:
                return {
                    "cycle_name": cycle_name,
                    "cycle_config": cycle_config,
                    "start_date": cycle_start,
                    "end_date": cycle_end,
                    "days_elapsed": (current_date - cycle_start).days,
                    "duration_days": duration,
                    "days_remaining": (cycle_end - current_date).days
                }
            cycle_start = cycle_end
            
        return {} # Done or not started yet

    def refresh_schedule(self):
        info = self.determine_current_cycle()
        if info:
            self.apply_cycle_schedule(info["cycle_config"], info["days_elapsed"])
            return info
        return None

    def get_cycle_info(self) -> Dict[str, Any]:
        info = self.determine_current_cycle()
        if not info:
             return {"status": "inactive", "total_days": (datetime.now() - self.start_date).days}
        
        # Calculate current dynamic hours for display
        start_h = info["cycle_config"].get("total_hours", 12)
        target_h = info["cycle_config"].get("target_total_hours", None)
        duration = info["duration_days"]
        days_passed = info["days_elapsed"]
        
        current_h = start_h
        if target_h is not None and duration > 1:
            progress = min(days_passed / (duration - 1), 1.0) if duration > 1 else 1.0
            current_h = start_h + (target_h - start_h) * progress

        res = {
             "status": "active",
             "total_days": (datetime.now() - self.start_date).days,
             "current_cycle": info["cycle_name"],
             "days_elapsed": info["days_elapsed"],
             "days_remaining": info["days_remaining"],
             "cycle_start_date": info["start_date"].isoformat(),
             "cycle_end_date": info["end_date"].isoformat(),
             "current_light_hours": round(current_h, 2),
             "schedule": info["cycle_config"]
        }
        return res
