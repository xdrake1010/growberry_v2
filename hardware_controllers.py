import RPi.GPIO as GPIO
import time
import json
import functools
import threading
from datetime import datetime
from typing import Dict, Optional, Callable

class LEDController:
    def __init__(self, led_pins: Dict[str, int]):
        self.led_pins = led_pins
        self.led_controls = self.create_led_controls()
        self.led_states = {
            name: {"state": False, "last_on": None, "last_off": None} for name in self.led_pins
        }
        self.lock = threading.Lock()

    def create_led_controls(self) -> Dict[str, Callable[[], None]]:
        led_controls = {}
        for name, pin in self.led_pins.items():
            led_controls[f"{name}_on"] = functools.partial(self.led_control, name, pin, True)
            led_controls[f"{name}_off"] = functools.partial(self.led_control, name, pin, False)
        return led_controls

    def led_control(self, led_name: str, led_pin: int, action: bool) -> None:
        with self.lock:
            if action:
                GPIO.output(led_pin, GPIO.LOW) # Turn ON
                self.led_states[led_name]["state"] = True
                self.led_states[led_name]["last_on"] = datetime.now()
                print(f'{led_name} ON')
            else:
                GPIO.output(led_pin, GPIO.HIGH) # Turn OFF
                self.led_states[led_name]["state"] = False
                self.led_states[led_name]["last_off"] = datetime.now()
                print(f'{led_name} OFF')

    def get_led_state(self, led_name: str) -> Dict[str, Optional[datetime]]:
        with self.lock:
            return self.led_states[led_name].copy()
            
    def get_all_states(self) -> Dict[str, dict]:
        with self.lock:
            return self.led_states.copy()

    def load_states(self, filepath: str) -> None:
        try:
            with open(filepath, 'r') as file:
                data = json.load(file)
            with self.lock:
                for target_pin in ["main", "ultrablue", "infrared"]:
                     state = data.get("leds", {}).get(target_pin, {}) if data.get("leds") else data.get(target_pin, {})
                     if state:
                          self.led_states[target_pin] = {
                              "state": state.get("state", False),
                              "last_on": datetime.fromisoformat(state["last_on"]) if state.get("last_on") else None,
                              "last_off": datetime.fromisoformat(state["last_off"]) if state.get("last_off") else None,
                          }
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Could not load LED states from {filepath}")


class VentilationController:
    def __init__(self, ventilation_pin: int):
        self.ventilation_pin = ventilation_pin
        self.state = False

    def control_ventilation(self, action: bool = True) -> None:
        if action:
            GPIO.output(self.ventilation_pin, GPIO.LOW)
            self.state = True
            print('Ventilation ON')
        else:
            GPIO.output(self.ventilation_pin, GPIO.HIGH)
            self.state = False
            print('Ventilation OFF')

    def get_state(self) -> bool:
        return self.state


class TankController:
    def __init__(self, tank_charge_pin: int, tank_sensor_pin: int):
        self.tank_charge_pin = tank_charge_pin
        self.tank_sensor_pin = tank_sensor_pin
        self.state = False

    def control_tank(self, action: bool = True, charge_time: int = 15) -> None:
        if action:
            start_time = time.time()
            GPIO.output(self.tank_charge_pin, GPIO.LOW)
            self.state = True
            print('Tank ON')
            # Assuming sensor is HIGH when NOT full, LOW when full
            while GPIO.input(self.tank_sensor_pin) == GPIO.HIGH and time.time() - start_time < charge_time:
                time.sleep(0.1)
            GPIO.output(self.tank_charge_pin, GPIO.HIGH)
            self.state = False
            print('Tank OFF')
        else:
            GPIO.output(self.tank_charge_pin, GPIO.HIGH)
            self.state = False
            print('Tank OFF')

    def get_state(self) -> bool:
        return self.state

class IrrigationController:
    def __init__(self, irrigation_pin: int, irrigation_timer: int = 5, multiplier: int = 1):
        self.irrigation_pin = irrigation_pin
        self.irrigation_timer = irrigation_timer
        self.multiplier = multiplier
        self.state = False

    def control_irrigation(self, irrigation_timer: Optional[int] = None, multiplier: Optional[int] = None) -> None:
        timer = irrigation_timer if irrigation_timer is not None else self.irrigation_timer
        mult = multiplier if multiplier is not None else self.multiplier

        start_time = time.time()
        GPIO.output(self.irrigation_pin, GPIO.LOW)
        self.state = True
        print('Irrigation ON')
        
        while time.time() - start_time < (timer * mult):
            time.sleep(1)
            
        GPIO.output(self.irrigation_pin, GPIO.HIGH)
        self.state = False
        print('Irrigation OFF')
        
    def get_state(self) -> bool:
        return self.state
