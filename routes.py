import shutil
import os
from flask import Blueprint, jsonify, request, Response, send_from_directory
from Adafruit_DHT import DHT11, read_retry
from config import GPIO_PINS, TIMELAPSE_BASE_DIR, load_plants_config, save_plants_config
from video_generator import EXPORTS_DIR

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
            "cycle_info": cycle_info,
            "active_cosecha": _system.active_cosecha
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
    success = _system.scheduled_timelapse(is_manual=True)
    if success:
        return jsonify({"status": "success", "message": "Captured and saved."})
    return jsonify({"status": "error", "message": "Failed to capture frame."}), 500

@api.route('/camera/status', methods=['GET'])
def get_camera_status():
    available = _system.camera_controller.check_available_cameras()
    return jsonify({
        "status": "online" if _system.camera_controller.shared_camera else "offline",
        "active_index": _system.camera_controller.camera_index,
        "available_indices": available,
        "is_streaming": _system.camera_controller.is_streaming,
        "client_count": _system.camera_controller.client_count
    })

@api.route('/timelapse/index', methods=['GET'])
def list_timelapse_images():
    """Returns a structured list of available images in data/timelapse"""
    try:
        data = []
        if not os.path.exists(TIMELAPSE_BASE_DIR):
            return jsonify([])
            
        for cosecha in sorted(os.listdir(TIMELAPSE_BASE_DIR)):
            cosecha_path = os.path.join(TIMELAPSE_BASE_DIR, cosecha)
            if not os.path.isdir(cosecha_path):
                continue
                
            cosecha_data = {"name": cosecha, "dates": []}
            
            for date_folder in sorted(os.listdir(cosecha_path), reverse=True):
                date_path = os.path.join(cosecha_path, date_folder)
                if not os.path.isdir(date_path):
                    continue
                    
                images = []
                for img in sorted(os.listdir(date_path), reverse=True):
                    if img.lower().endswith(('.jpg', '.jpeg', '.png')):
                        # Relative path for the view route
                        rel_path = f"{cosecha}/{date_folder}/{img}"
                        images.append({
                            "name": img,
                            "url": f"/api/timelapse/image/{rel_path}",
                            "timestamp": img.split('.')[0]
                        })
                
                if images:
                    cosecha_data["dates"].append({
                        "date": date_folder,
                        "images": images
                    })
            
            if cosecha_data["dates"]:
                data.append(cosecha_data)
                
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@api.route('/timelapse/image/<path:filename>', methods=['GET'])
def view_timelapse_image(filename):
    """Serves an image from the TIMELAPSE_BASE_DIR"""
    return send_from_directory(TIMELAPSE_BASE_DIR, filename)

@api.route('/timelapse/delete/image/<cosecha>/<date>/<filename>', methods=['DELETE'])
def delete_timelapse_image(cosecha, date, filename):
    """Deletes a specific image file."""
    try:
        rel_path = f"{cosecha}/{date}/{filename}"
        target_path = os.path.abspath(os.path.join(TIMELAPSE_BASE_DIR, rel_path))
        
        if not target_path.startswith(os.path.abspath(TIMELAPSE_BASE_DIR)):
            return jsonify({"status": "error", "message": "Unauthorized path"}), 403
            
        if os.path.exists(target_path):
            os.remove(target_path)
            # Check if parent directory is empty and delete it if it is
            date_dir = os.path.dirname(target_path)
            if not os.listdir(date_dir):
                os.rmdir(date_dir)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "File not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@api.route('/timelapse/delete/folder/<cosecha>/<date>', methods=['DELETE'])
def delete_timelapse_folder(cosecha, date):
    """Deletes a complete date folder."""
    try:
        rel_path = f"{cosecha}/{date}"
        target_path = os.path.abspath(os.path.join(TIMELAPSE_BASE_DIR, rel_path))
        
        if not target_path.startswith(os.path.abspath(TIMELAPSE_BASE_DIR)):
            return jsonify({"status": "error", "message": "Unauthorized path"}), 403
            
        if os.path.exists(target_path) and os.path.isdir(target_path):
            shutil.rmtree(target_path)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Folder not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@api.route('/timelapse/delete/cosecha/<cosecha>', methods=['DELETE'])
def delete_cosecha(cosecha):
    """Deletes an entire harvest catalog."""
    try:
        target_path = os.path.abspath(os.path.join(TIMELAPSE_BASE_DIR, cosecha))
        
        if not target_path.startswith(os.path.abspath(TIMELAPSE_BASE_DIR)):
            return jsonify({"status": "error", "message": "Unauthorized path"}), 403
            
        if os.path.exists(target_path) and os.path.isdir(target_path):
            shutil.rmtree(target_path)
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Cosecha not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@api.route('/timelapse/delete/video/<filename>', methods=['DELETE'])
def delete_video(filename):
    """Deletes an exported video file."""
    success, message = _system.video_generator.delete_video(filename)
    if success:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": message}), 400

@api.route('/configs', methods=['GET'])
def get_configs():
    return jsonify(load_plants_config())

@api.route('/configs', methods=['POST'])
def set_configs():
    new_data = request.json
    save_plants_config(new_data)
    
    # Hot-reload system 
    _system.config_data = new_data
    _system.active_cosecha = new_data.get("active_cosecha", "default")
    _system.camera_controller.set_cosecha_name(_system.active_cosecha)
    _system.schedule_manager.reload_config(new_data)
    _system.schedule_manager.refresh_schedule()
    _system.rebuild_scheduler() # Apply dynamic background tasks
    return jsonify({"status": "success", "message": "Config updated"})

@api.route('/history', methods=['GET'])
def get_history():
    sensor = request.args.get('sensor', 'temperature')
    limit = request.args.get('limit', default=100, type=int) 
    harvest = request.args.get('harvest', None)
    
    history = _system.db_manager.get_history(sensor, harvest=harvest, limit=limit)
    return jsonify(history)

@api.route('/timelapse/export', methods=['POST'])
def export_timelapse():
    cosecha = request.json.get('cosecha', _system.active_cosecha)
    fps = request.json.get('fps', 10)
    date_from = request.json.get('date_from')
    date_to = request.json.get('date_to')
    
    success, message = _system.video_generator.export_cosecha(cosecha, fps, date_from, date_to)
    if success:
        return jsonify({"status": "success", "message": message})
    return jsonify({"status": "error", "message": message}), 400

@api.route('/timelapse/exports', methods=['GET'])
def list_exports():
    return jsonify(_system.video_generator.list_exports())

@api.route('/timelapse/download/<filename>', methods=['GET'])
def download_video(filename):
    return send_from_directory(EXPORTS_DIR, filename, as_attachment=True)

@api.route('/harvests/info', methods=['GET'])
def get_harvests_info():
    """Returns available date ranges and start dates for all harvests."""
    config = load_plants_config()
    info = {}
    
    # Get configuration start dates
    for name, data in config.get("plants", {}).items():
        info[name] = {
            "config_start": data.get("start_date"),
            "first_image": None,
            "last_image": None
        }
        
        # Check actual image dates in filesystem
        cosecha_path = os.path.join(TIMELAPSE_BASE_DIR, name)
        if os.path.exists(cosecha_path):
            dates = sorted([d for d in os.listdir(cosecha_path) if os.path.isdir(os.path.join(cosecha_path, d))])
            if dates:
                info[name]["first_image"] = dates[0]
                info[name]["last_image"] = dates[-1]
                
    return jsonify(info)

@api.route('/harvests/<name>', methods=['DELETE'])
def delete_harvest_plan(name):
    """Deletes a harvest plan configuration from plants_config.json."""
    try:
        config = load_plants_config()
        if name in config.get("plants", {}):
            # Safety: don't delete the only harvest
            if len(config["plants"]) <= 1:
                return jsonify({"status": "error", "message": "Cannot delete the last remaining plan."}), 400
                
            # If deleting the active harvest, switch to another one
            if config.get("active_cosecha") == name:
                remaining = [k for k in config["plants"].keys() if k != name]
                config["active_cosecha"] = remaining[0]
            
            del config["plants"][name]
            save_plants_config(config)
            
            # Trigger hot-reload (same as set_configs but partial)
            _system.config_data = config
            _system.active_cosecha = config.get("active_cosecha")
            _system.camera_controller.set_cosecha_name(_system.active_cosecha)
            _system.schedule_manager.reload_config(config)
            _system.schedule_manager.refresh_schedule()
            _system.rebuild_scheduler()
            
            return jsonify({"status": "success", "message": f"Plan '{name}' deleted."})
        return jsonify({"status": "error", "message": "Plan not found."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
