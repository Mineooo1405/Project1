import json
import logging
import datetime
import traceback
from typing import Dict, Any, Optional, List
from database import EncoderData, BNO055Data, LogData

logger = logging.getLogger("json_handler")

class JSONDataHandler:
    """
    Xử lý và chuyển đổi dữ liệu JSON giữa các định dạng khác nhau
    """
    
    @staticmethod
    def serialize_datetime(obj: Any) -> str:
        """
        Hàm helper để chuyển đổi đối tượng datetime thành chuỗi ISO
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    @staticmethod
    def parse_json(json_str: str) -> Optional[Dict]:
        """
        Parse chuỗi JSON thành object, xử lý các lỗi
        
        Args:
            json_str: Chuỗi JSON cần parse
            
        Returns:
            Dict object hoặc None nếu có lỗi
        """
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}")
            logger.debug(f"JSON string: {json_str[:100]}...")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON: {e}")
            logger.error(traceback.format_exc())
            return None
    
    @staticmethod
    def to_json(obj: Any) -> str:
        """
        Chuyển đổi object thành chuỗi JSON, xử lý các kiểu dữ liệu đặc biệt
        
        Args:
            obj: Đối tượng cần chuyển đổi
            
        Returns:
            Chuỗi JSON
        """
        try:
            return json.dumps(obj, default=JSONDataHandler.serialize_datetime)
        except Exception as e:
            logger.error(f"Error converting to JSON: {e}")
            logger.error(traceback.format_exc())
            # Trả về object đơn giản nhất có thể serialize được
            return json.dumps({"error": str(e)})
    
    @staticmethod
    def convert_keys_to_camel_case(obj: Dict) -> Dict:
        """
        Chuyển đổi các khóa từ snake_case sang camelCase
        
        Args:
            obj: Dict với các khóa snake_case
            
        Returns:
            Dict với các khóa camelCase
        """
        if not isinstance(obj, dict):
            return obj
            
        result = {}
        for key, value in obj.items():
            # Chuyển đổi khóa sang camelCase
            words = key.split('_')
            camel_key = words[0] + ''.join(word.capitalize() for word in words[1:])
            result[camel_key] = value
            
        return result
    
    @staticmethod
    def store_json_message(db, message: Dict[str, Any]):
        """
        Lưu trữ tin nhắn JSON vào database dựa trên loại dữ liệu
        """
        if not isinstance(message, dict):
            logger.warning(f"Invalid message format: {message}")
            return None
        
        message_type = message.get("type")
        robot_id = message.get("robot_id", 1)
        
        if message_type == "encoder_data":
            return JSONDataHandler._store_encoder_data(db, message, robot_id)
        elif message_type == "imu_data":
            return JSONDataHandler._store_imu_data(db, message, robot_id)
        elif message_type == "log_data":
            return JSONDataHandler._store_log_data(db, message, robot_id)
        else:
            logger.warning(f"Unknown message type: {message_type}")
            return None
    
    @staticmethod
    def _store_encoder_data(db, message: Dict[str, Any], robot_id):
        """Lưu trữ dữ liệu encoder vào database"""
        try:
            # Lấy giá trị từ tin nhắn
            data_values = message.get("data", [0, 0, 0])
            if not isinstance(data_values, list):
                data_values = [0, 0, 0]
            
            # Đảm bảo đủ 3 giá trị
            while len(data_values) < 3:
                data_values.append(0.0)
            
            # Tạo bản ghi mới
            encoder_data = EncoderData(
                robot_id=robot_id,
                data_value1=data_values[0],
                data_value2=data_values[1],
                data_value3=data_values[2],
                source_file="websocket",
                created_at=datetime.datetime.utcnow()
            )
            
            db.add(encoder_data)
            db.commit()
            
            logger.debug(f"Stored encoder data for robot {robot_id}")
            return encoder_data
        except Exception as e:
            db.rollback()
            logger.error(f"Error storing encoder data: {e}")
            return None
    
    @staticmethod
    def _store_imu_data(db, message: Dict[str, Any], robot_id):
        """Lưu trữ dữ liệu IMU vào database"""
        try:
            # Lấy dữ liệu IMU từ message
            orientation = message.get("orientation", {})
            euler_roll = orientation.get("roll", 0.0)
            euler_pitch = orientation.get("pitch", 0.0)
            euler_yaw = orientation.get("yaw", 0.0)
            
            # Lấy dữ liệu quaternion nếu có
            quaternion = message.get("quaternion", [1.0, 0.0, 0.0, 0.0])
            if not isinstance(quaternion, list) or len(quaternion) < 4:
                quaternion = [1.0, 0.0, 0.0, 0.0]
            
            # Tạo bản ghi mới
            imu_data = BNO055Data(
                robot_id=robot_id,
                sensor_time=int(datetime.datetime.now().timestamp()),
                euler_roll=euler_roll,
                euler_pitch=euler_pitch,
                euler_yaw=euler_yaw,
                quaternion_w=quaternion[0],
                quaternion_x=quaternion[1],
                quaternion_y=quaternion[2],
                quaternion_z=quaternion[3],
                source_file="websocket",
                created_at=datetime.datetime.utcnow()
            )
            
            db.add(imu_data)
            db.commit()
            
            logger.debug(f"Stored IMU data for robot {robot_id}")
            return imu_data
        except Exception as e:
            db.rollback()
            logger.error(f"Error storing IMU data: {e}")
            return None
    
    @staticmethod
    def _store_log_data(db, message: Dict[str, Any], robot_id):
        """Lưu trữ dữ liệu log vào database"""
        try:
            # Lấy nội dung log
            log_message = message.get("message", "")
            
            # Tạo bản ghi mới
            log_data = LogData(
                robot_id=robot_id,
                message=log_message,
                source_file="websocket",
                created_at=datetime.datetime.utcnow()
            )
            
            db.add(log_data)
            db.commit()
            
            logger.debug(f"Stored log message for robot {robot_id}")
            return log_data
        except Exception as e:
            db.rollback()
            logger.error(f"Error storing log data: {e}")
            return None