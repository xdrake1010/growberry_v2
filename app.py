import time
import schedule
import threading
import RPi.GPIO as GPIO
from flask import Flask, Response, jsonify
from flask_cors import CORS
from routes import api, init_routes
from hardware_controllers import LEDController, VentilationController, TankController, IrrigationController
from schedule_controller import ScheduleManager
from camera_controller import CameraController
from config import GPIO_PINS, load_plants_config, save_plants_config

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

class ApplicationSystem:
    def __init__(self):
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
        
        self.lock = threading.Lock()
        
    def daemon_loop(self):
        # Initial schedule setup
        self.schedule_manager.refresh_schedule()
        
        # Every hour, capture timelapse frame
        schedule.every(1).hours.do(self.camera_controller.capture_timelapse_frame)
        
        # Every day, we verify if cycle phase needs to be updated
        schedule.every().day.at("00:01").do(self.schedule_manager.refresh_schedule)
        
        while True:
            with self.lock:
                schedule.run_pending()
            time.sleep(30)

system = ApplicationSystem()
init_routes(system)
app.register_blueprint(api, url_prefix='/api')

@app.route('/')
def index():
    return app.send_static_file('index.html')

if __name__ == '__main__':
    daemon_thread = threading.Thread(target=system.daemon_loop, daemon=True)
    daemon_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
