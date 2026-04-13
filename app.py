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
            self.config_data
        )
        self.camera_controller = CameraController(cosecha_name=self.active_cosecha)
        self.video_generator = VideoGenerator()
        
        # Sensor Cache
        self.sensor_data = {"temperature": None, "humidity": None, "last_update": None}
        
        self.lock = threading.Lock()
        logger.info("System Initialized Successfully.")
        
    def rebuild_scheduler(self):
        """Standardized method to initialize or refresh all background scheduled tasks."""
        logger.info("[SCHEDULER] Rebuilding background tasks...")
        
        # Clear existing jobs if any (using tags for precision)
        schedule.clear('background_tasks')

        # 1. Daily refresh (Cycle phase verification)
        schedule.every().day.at("00:01").do(self.schedule_manager.refresh_schedule).tag('background_tasks')

    def log_sensors(self):
        """Saves current cached sensor data to the database for history."""
        with self.lock:
            t = self.sensor_data.get("temperature")
            h = self.sensor_data.get("humidity")
        
        if t is not None and h is not None:
            self.db_manager.save_measurement("temperature", t)
            self.db_manager.save_measurement("humidity", h)
            logger.info(f"Historical Log: T={t}C, H={h}% saved to DB.")
        else:
            logger.warning("Historical Log skipped: No sensor data in cache.")

    def scheduled_timelapse(self):
        """Capture a timelapse frame with current sensor metadata, handling night flash if needed."""
        with self.lock:
            temp = self.sensor_data.get("temperature")
            hum = self.sensor_data.get("humidity")
            harvest = self.active_cosecha
        
        # Flash logic: if all lights are off, pulse main white for 2 seconds
        restore_main = False
        all_states = self.led_controller.get_all_states()
        if not any(info["state"] for info in all_states.values()):
            logger.info("[TIMELAPSE] Dark detected. Pulsing Main White for 2s...")
            self.led_controller.led_control("main", GPIO_PINS["main_led"], True)
            time.sleep(2) # Wait for camera exposure
            restore_main = True
        
        metadata = {"temp": temp, "hum": hum, "harvest": harvest}
        success = self.camera_controller.capture_timelapse_frame(metadata=metadata)
        
        if restore_main:
            self.led_controller.led_control("main", GPIO_PINS["main_led"], False)
            
        return success

    def rebuild_scheduler(self):
        """Standardized method to initialize or refresh all background scheduled tasks."""
        logger.info("[SCHEDULER] Rebuilding background tasks...")
        
        # Clear existing jobs if any (using tags for precision)
        schedule.clear('background_tasks')

        # 1. Daily refresh (Cycle phase verification)
        schedule.every().day.at("00:01").do(self.schedule_manager.refresh_schedule).tag('background_tasks')

        # 2. Sequential Sensor Logging for History (every 15 mins)
        schedule.every(15).minutes.do(self.log_sensors).tag('background_tasks')

        # 3. Dynamic Timelapse Capture
        enabled = self.config_data.get("timelapse_enabled", True)
        interval = self.config_data.get("timelapse_interval_minutes", 60)
        
        if enabled:
            schedule.every(interval).minutes.do(self.scheduled_timelapse).tag('background_tasks')
            logger.info(f"[SCHEDULER] Automatic timelapse enabled every {interval} minutes.")
        else:
            logger.info("[SCHEDULER] Automatic timelapse is DISABLED.")

    def daemon_loop(self):
        logger.info("Starting background daemon thread...")
        
        # Initialize the dynamic scheduler
        self.rebuild_scheduler()
        
        # Initial schedule setup from manager
        self.schedule_manager.refresh_schedule()
        
        # Initial log on startup
        threading.Timer(5, lambda: self.db_manager.save_measurement("heartbeat", 1)).start()
        # Immediate logging to populate charts faster
        self.log_sensors()
        
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
                # IMPORTANT: Run pending WITHOUT the global lock to avoid deadlock
                # inside scheduled jobs like log_sensors() which try to acquire self.lock
                schedule.run_pending()
            except Exception as e:
                logger.error(f"Error in daemon loop: {e}")
            time.sleep(10) # 10s resolution is enough for 15+ min tasks

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
