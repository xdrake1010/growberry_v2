import time
import schedule
import threading
import logging
from datetime import datetime
import RPi.GPIO as GPIO
from flask import Flask, Response, jsonify
from flask_cors import CORS
from routes import api, init_routes
from hardware_controllers import LEDController, VentilationController, TankController, IrrigationController
from schedule_controller import ScheduleManager
from camera_controller import CameraController
from database_manager import DatabaseManager
from video_generator import VideoGenerator
from config import GPIO_PINS, load_plants_config, save_plants_config, setup_logging

# Initialize logging
setup_logging()
logger = logging.getLogger("Growberry")

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

class ApplicationSystem:
    def __init__(self):
        logger.info("Initializing Application System...")
        self.lock = threading.Lock()
        self.scheduler_lock = threading.Lock()
        
        # Initialize GPIO globally and set up pins
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        
        # Set starting state for relays (HIGH = OFF for active-low relays)
        out_pins = [
            GPIO_PINS['main_led'], GPIO_PINS['infrared_led'], GPIO_PINS['ultrablue_led'],
            GPIO_PINS['ventilation'], GPIO_PINS['irrigation'], GPIO_PINS['tank_charge']
        ]
        for pin in out_pins:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
            
        # Set up input sensors
        GPIO.setup(GPIO_PINS['tank_sensor'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Init Database
        self.db_manager = DatabaseManager()
        
        self.config_data = load_plants_config()
        self.active_cosecha = self.config_data.get("active_cosecha", "default")
        
        # Init Hardware Subsystems
        self.led_controller = LEDController({
            "main": GPIO_PINS["main_led"],
            "infrared": GPIO_PINS["infrared_led"],
            "ultrablue": GPIO_PINS["ultrablue_led"]
        })
        self.ventilation_controller = VentilationController(GPIO_PINS["ventilation"])
        self.tank_controller = TankController(GPIO_PINS["tank_charge"], GPIO_PINS["tank_sensor"])
        self.irrigation_controller = IrrigationController(GPIO_PINS["irrigation"])
        
        # Init Software Managers 
        self.schedule_manager = ScheduleManager(
            self.led_controller, 
            self.tank_controller, 
            self.irrigation_controller, 
            self.config_data,
            self.scheduler_lock
        )
        self.camera_controller = CameraController(cosecha_name=self.active_cosecha)
        self.video_generator = VideoGenerator()
        
        # Sensor Cache
        self.sensor_data = {"temperature": None, "humidity": None, "last_update": None}
        
        logger.info("System Initialized Successfully.")
        

    def log_sensors(self):
        """Saves current cached sensor data to the database for history."""
        try:
            with self.lock:
                t = self.sensor_data.get("temperature")
                h = self.sensor_data.get("humidity")
            
            if t is not None and h is not None:
                self.db_manager.save_measurement("temperature", t, harvest=self.active_cosecha)
                self.db_manager.save_measurement("humidity", h, harvest=self.active_cosecha)
                logger.info(f"Historical Log: T={t}C, H={h}% saved to DB for {self.active_cosecha}.")
            else:
                logger.warning("Historical Log skipped: No sensor data in cache yet.")
        except Exception as e:
            logger.error(f"Error in log_sensors: {e}")

    def scheduled_timelapse(self, is_manual=False):
        """Capture a timelapse frame with current sensor metadata, handling night flash if needed."""
        # Check lighting state
        all_states = self.led_controller.get_all_states()
        any_light_on = any(info["state"] for info in all_states.values())
        
        # Plant stress safety: Skip auto-timelapse if dark
        if not any_light_on and not is_manual:
            logger.info("[TIMELAPSE] Dark cycle detected. Skipping automatic capture to prevent plant stress.")
            return False

        # Flash logic for Manual captures during night
        restore_main = False
        if not any_light_on and is_manual:
            logger.info("[TIMELAPSE] Dark detected + Manual request. Pulsing Main White for 2s...")
            self.led_controller.led_control("main", GPIO_PINS["main_led"], True)
            time.sleep(2) # Wait for camera exposure
            restore_main = True
        
        with self.lock:
            temp = self.sensor_data.get("temperature")
            hum = self.sensor_data.get("humidity")
            harvest = self.active_cosecha
        
        metadata = {"temp": temp, "hum": hum, "harvest": harvest}
        success = self.camera_controller.capture_timelapse_frame(metadata=metadata)
        
        if success:
            logger.info(f"[TIMELAPSE] {'Manual' if is_manual else 'Automatic'} capture SUCCESSFUL.")
        else:
            logger.error(f"[TIMELAPSE] {'Manual' if is_manual else 'Automatic'} capture FAILED.")
            
        if restore_main:
            self.led_controller.led_control("main", GPIO_PINS["main_led"], False)
            
        return success

    def rebuild_scheduler(self):
        """Standardized method to initialize or refresh all background scheduled tasks."""
        logger.info("[SCHEDULER] Rebuilding background tasks...")
        
        with self.scheduler_lock:
            # Clear existing jobs if any (using tags for precision)
            schedule.clear('background_tasks')

            # 1. Daily refresh (Cycle phase verification)
            schedule.every().day.at("00:01").do(self.schedule_manager.refresh_schedule).tag('background_tasks')

            # 2. Sequential Sensor Logging for History (Custom Interval)
            log_interval = self.config_data.get("sensor_log_interval_minutes", 1)
            schedule.every(log_interval).minutes.do(self.log_sensors).tag('background_tasks')
            logger.info(f"[SCHEDULER] Sensor logging enabled every {log_interval} minutes.")

            # 3. Dynamic Timelapse Capture
            enabled = self.config_data.get("timelapse_enabled", True)
            interval = self.config_data.get("timelapse_interval_minutes", 60)
            
            if enabled:
                schedule.every(interval).minutes.do(lambda: self.scheduled_timelapse(is_manual=False)).tag('background_tasks')
                logger.info(f"[SCHEDULER] Automatic timelapse enabled every {interval} minutes.")
            else:
                logger.info("[SCHEDULER] Automatic timelapse is DISABLED.")

    def daemon_loop(self):
        logger.info("Starting background daemon thread...")
        
        # Initialize the dynamic scheduler
        self.rebuild_scheduler()
        
        # Initial schedule setup from manager
        self.schedule_manager.refresh_schedule()
        
        # Initial log with delay to ensure cache is populated
        threading.Timer(5, lambda: self.db_manager.save_measurement("heartbeat", 1, harvest=self.active_cosecha)).start()
        threading.Timer(45, self.log_sensors).start()
        
        # New: Continuous cache update every 30 seconds
        def update_cache_loop():
            from Adafruit_DHT import DHT11, read_retry
            while True:
                try:
                    h, t = read_retry(DHT11, GPIO_PINS["dht11_sensor"])
                    if t is not None and h is not None:
                        with self.lock:
                            self.sensor_data["temperature"] = t
                            self.sensor_data["humidity"] = h
                            self.sensor_data["last_update"] = datetime.now().isoformat()
                except Exception as e:
                    logger.error(f"Error updating sensor cache: {e}")
                time.sleep(30) # Read every 30 seconds

        cache_thread = threading.Thread(target=update_cache_loop, daemon=True)
        cache_thread.start()
        
        while True:
            try:
                # IMPORTANT: Run pending with a lock to avoid corruption from Flask threads
                with self.scheduler_lock:
                    schedule.run_pending()
            except Exception as e:
                logger.error(f"Error in daemon loop: {e}")
            time.sleep(10) # 10s resolution is enough for 1+ min tasks

system = ApplicationSystem()
init_routes(system)
app.register_blueprint(api, url_prefix='/api')

@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    daemon_thread = threading.Thread(target=system.daemon_loop, daemon=True)
    daemon_thread.start()
    
    logger.info("Starting Flask server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
