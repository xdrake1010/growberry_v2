import os
from flask import Blueprint, jsonify, request, Response
from Adafruit_DHT import DHT11, read_retry
from config import GPIO_PINS, TIMELAPSE_BASE_DIR, load_plants_config, save_plants_config

api = Blueprint('api', __name__)
_system = None

def init_routes(system_instance):
    global _system
    _system = system_instance

@api.route('/video_feed')
def video_feed():
    if not _system:
        return "System Not Init", 500
    return Response(_system.camera_controller.generate_live_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@api.route('/statistics', methods=['GET'])
def get_statistics():
    try:
        # Using Cached Sensor Data to keep CPU load low on Pi Zero
        temperature = _system.sensor_data["temperature"]
        humidity = _system.sensor_data["humidity"]
        last_update = _system.sensor_data["last_update"]
        
        cycle_info = _system.schedule_manager.get_cycle_info()
        led_info = _system.led_controller.get_all_states()
        ventilation_state = _system.ventilation_controller.get_state()
        tank_state = _system.tank_controller.get_state()
        irrigation_state = _system.irrigation_controller.get_state()
        
        return jsonify({
            "temperature": temperature,
            "humidity": humidity,
            "last_update": last_update,
            "ventilation": ventilation_state,
            "tank": tank_state,
            "irrigation": irrigation_state,
            "leds": led_info,
            "cycle_info": cycle_info
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@api.route('/led/<led>/<action>', methods=['GET'])
def control_led(led, action):
    try:
        control_method = _system.led_controller.led_controls.get(f"{led}_{action}")
        if control_method:
            control_method()
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Invalid LED or action"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@api.route('/ventilation/<action>', methods=['GET'])
def control_ventilation(action):
    if action == "on":
        _system.ventilation_controller.control_ventilation(True)
    elif action == "off":
         _system.ventilation_controller.control_ventilation(False)
    else:
         return jsonify({"status": "error", "message": "Invalid action"}), 400
    return jsonify({"status": "success"})

@api.route('/tank/<action>', methods=['GET'])
def control_tank(action):
    charge_time = request.args.get('charge_time', default=15, type=int)
    if action == "on":
        _system.tank_controller.control_tank(True, charge_time)
    elif action == "off":
        _system.tank_controller.control_tank(False)
    else:
        return jsonify({"status": "error", "message": "Invalid action"}), 400
    return jsonify({"status": "success"})

@api.route('/irrigation/<action>', methods=['GET'])
def control_irrigation(action):
    if action == "on":
        _system.irrigation_controller.control_irrigation()
    elif action == "off":
        import RPi.GPIO as GPIO
        GPIO.output(_system.irrigation_controller.irrigation_pin, GPIO.HIGH)
        _system.irrigation_controller.state = False
    return jsonify({"status": "success"})

@api.route('/timelapse/capture', methods=['POST'])
def manual_timelapse_capture():
    success = _system.camera_controller.capture_timelapse_frame()
    if success:
        return jsonify({"status": "success", "message": "Captured and saved."})
    return jsonify({"status": "error", "message": "Failed to capture frame."}), 500

@api.route('/configs', methods=['GET'])
def get_configs():
    return jsonify(load_plants_config())

@api.route('/configs', methods=['POST'])
def set_configs():
    new_data = request.json
    save_plants_config(new_data)
    
    # Hot-reload system 
    _system.config_data = new_data
    _system.schedule_manager.cycles = new_data.get("plants", {}).get("default", {}).get("cycles", {})
    _system.schedule_manager.refresh_schedule()
    return jsonify({"status": "success", "message": "Config updated"})

@api.route('/history', methods=['GET'])
def get_history():
    sensor = request.args.get('sensor', 'temperature')
    limit = request.args.get('limit', default=48, type=int) # 48 entries x 15 mins = 12 hours
    history = _system.db_manager.get_history(sensor, limit)
    return jsonify(history)
