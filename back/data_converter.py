import datetime
import json
from typing import List, Dict, Any, Optional
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger("data_converter")

class DataConverter:
    @staticmethod
    def imu_to_frontend(imu_data) -> Dict[str, Any]:
        """Chuyển đổi IMU data từ database model sang định dạng JSON cho frontend"""
        result = {
            "timestamp": imu_data.timestamp.isoformat() if hasattr(imu_data, "timestamp") and imu_data.timestamp else datetime.datetime.now().isoformat(),
            "acceleration": {
                "x": float(imu_data.accel_x) if hasattr(imu_data, "accel_x") else 0,
                "y": float(imu_data.accel_y) if hasattr(imu_data, "accel_y") else 0,
                "z": float(imu_data.accel_z) if hasattr(imu_data, "accel_z") else 0
            },
            "angular_velocity": {
                "x": float(imu_data.gyro_x) if hasattr(imu_data, "gyro_x") else 0,
                "y": float(imu_data.gyro_y) if hasattr(imu_data, "gyro_y") else 0, 
                "z": float(imu_data.gyro_z) if hasattr(imu_data, "gyro_z") else 0
            }
        }

        # Lấy orientation từ raw_data nếu có
        orientation = {"roll": 0, "pitch": 0, "yaw": 0}
        
        if hasattr(imu_data, "raw_data") and imu_data.raw_data:
            raw_data = imu_data.raw_data
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except:
                    raw_data = {}
            
            if isinstance(raw_data, dict) and "orientation" in raw_data:
                orientation = raw_data["orientation"]
        
        result["orientation"] = orientation
        return result
    
    @staticmethod
    def trajectory_to_frontend(trajectory_data) -> Dict[str, Any]:
        """Chuyển đổi Trajectory data từ database model sang định dạng JSON cho frontend"""
        result = {
            "timestamp": trajectory_data.timestamp.isoformat() if hasattr(trajectory_data, "timestamp") and trajectory_data.timestamp else datetime.datetime.now().isoformat(),
            "current_position": {
                "x": float(trajectory_data.current_x) if hasattr(trajectory_data, "current_x") else 0, 
                "y": float(trajectory_data.current_y) if hasattr(trajectory_data, "current_y") else 0,
                "theta": float(trajectory_data.current_theta) if hasattr(trajectory_data, "current_theta") else 0
            },
            "status": trajectory_data.status if hasattr(trajectory_data, "status") else "unknown",
            "progress_percent": float(trajectory_data.progress_percent) if hasattr(trajectory_data, "progress_percent") else 0
        }
        
        # Target position now comes from raw_data if available
        if hasattr(trajectory_data, "raw_data") and trajectory_data.raw_data:
            raw_data = trajectory_data.raw_data
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except:
                    raw_data = {}
                    
            # Get target from raw_data
            target_x = raw_data.get("target_x", 0)
            target_y = raw_data.get("target_y", 0)
            target_theta = raw_data.get("target_theta", 0)
            
            result["target_position"] = {
                "x": float(target_x),
                "y": float(target_y),
                "theta": float(target_theta)
            }
        else:
            # Default target position if not available
            result["target_position"] = {
                "x": 0.0,
                "y": 0.0,
                "theta": 0.0
            }
        
        # Xử lý points
        if hasattr(trajectory_data, "points") and trajectory_data.points:
            if isinstance(trajectory_data.points, dict):
                result["points"] = trajectory_data.points
            else:
                # Nếu points không phải là dict, thử chuyển đổi
                try:
                    if isinstance(trajectory_data.points, str):
                        result["points"] = json.loads(trajectory_data.points)
                    else:
                        result["points"] = {"x": [], "y": [], "theta": []}
                except:
                    result["points"] = {"x": [], "y": [], "theta": []}
        else:
            result["points"] = {"x": [], "y": [], "theta": []}
            
        return result
    
    @staticmethod
    def encoder_to_frontend(encoder_data) -> Dict[str, Any]:
        """Chuyển đổi Encoder data từ database model sang định dạng JSON cho frontend"""
        # Đảm bảo rpm là mảng với 3 phần tử
        rpm = [0, 0, 0]
        
        if hasattr(encoder_data, "rpm") and encoder_data.rpm:
            if isinstance(encoder_data.rpm, list):
                for i, val in enumerate(encoder_data.rpm[:3]):
                    rpm[i] = float(val)
        
        return {
            "timestamp": encoder_data.timestamp.isoformat() if hasattr(encoder_data, "timestamp") and encoder_data.timestamp else datetime.datetime.now().isoformat(),
            "rpm": rpm
        }
    
    @staticmethod
    def pid_to_frontend(pid_config) -> Dict[str, Any]:
        """Chuyển đổi PID config từ database model sang định dạng JSON cho frontend"""
        return {
            "motor_id": pid_config.motor_id if hasattr(pid_config, "motor_id") else 0,
            "kp": float(pid_config.kp) if hasattr(pid_config, "kp") else 0,
            "ki": float(pid_config.ki) if hasattr(pid_config, "ki") else 0,
            "kd": float(pid_config.kd) if hasattr(pid_config, "kd") else 0,
            "timestamp": pid_config.timestamp.isoformat() if hasattr(pid_config, "timestamp") and pid_config.timestamp else datetime.datetime.now().isoformat()
        }

    @staticmethod
    def get_latest_data_by_robot(db: Session, model_class, robot_id: str, limit: int = 1):
        """Lấy dữ liệu mới nhất từ database cho một robot cụ thể"""
        try:
            query = db.query(model_class).filter(model_class.robot_id == robot_id)
            query = query.order_by(model_class.timestamp.desc()).limit(limit)
            return query.all()
        except Exception as e:
            logger.error(f"Error querying {model_class.__name__} for robot {robot_id}: {str(e)}")
            return []