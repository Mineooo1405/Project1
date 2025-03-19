import math
import datetime
import logging
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from database import TrajectoryData, SessionLocal

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trajectory_service")

class TrajectoryService:
    # Lưu trữ vị trí và quỹ đạo của mỗi robot trong bộ nhớ
    robot_positions = {}
    
    @classmethod
    def initialize_robot_position(cls, robot_id: str):
        """Khởi tạo vị trí robot về (0,0,0) và quỹ đạo rỗng"""
        cls.robot_positions[robot_id] = {
            "x": 0.0,
            "y": 0.0,
            "theta": 0.0,
            "points": {
                "x": [0.0],
                "y": [0.0],
                "theta": [0.0]
            },
            "last_update": datetime.datetime.now(),
            "saved_points_count": 1  # Số lượng điểm đã lưu vào database
        }
        logger.info(f"Initialized trajectory for robot {robot_id} at (0,0,0)")
        return cls.robot_positions[robot_id]
    
    @classmethod
    def get_robot_position(cls, robot_id: str) -> Dict[str, Any]:
        """Lấy vị trí hiện tại của robot"""
        if robot_id not in cls.robot_positions:
            return cls.initialize_robot_position(robot_id)
        return cls.robot_positions[robot_id]
    
    @classmethod
    def calculate_position_from_encoder(cls, robot_id: str, encoder_data: Dict[str, Any], imu_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Tính vị trí mới của robot dựa trên dữ liệu encoder và IMU
        
        Parameters:
        -----------
        robot_id: str
            ID của robot
        encoder_data: Dict
            Dữ liệu encoder {"rpm": [rpm1, rpm2, rpm3], "timestamp": timestamp}
        imu_data: Dict, optional
            Dữ liệu IMU {"orientation": {"roll", "pitch", "yaw"}, ...}
            
        Returns:
        --------
        Dict: Vị trí mới của robot và quỹ đạo cập nhật
        """
        # Khởi tạo vị trí nếu chưa có
        if robot_id not in cls.robot_positions:
            cls.initialize_robot_position(robot_id)
        
        position = cls.robot_positions[robot_id]
        
        # Lấy thời gian hiện tại và tính delta_t
        now = datetime.datetime.now()
        last_update = position["last_update"]
        delta_t = (now - last_update).total_seconds()  # Thời gian từ lần cập nhật trước, tính bằng giây
        
        # Giới hạn delta_t để tránh các bước nhảy lớn
        if delta_t > 1.0:
            delta_t = 0.1  # Giá trị mặc định nếu delta_t quá lớn
            
        # Tránh delta_t = 0 để không gây lỗi chia cho 0
        if delta_t < 0.001:
            return position
        
        # Lấy RPM từ encoder data
        rpm = encoder_data.get("rpm", [0, 0, 0])
        if not rpm or len(rpm) < 3:
            rpm = [0, 0, 0]  # RPM mặc định nếu không có dữ liệu
            
        # Các thông số của robot (cần điều chỉnh theo robot thực tế)
        wheel_radius = 0.05  # Bán kính bánh xe (m)
        robot_radius = 0.15  # Khoảng cách từ tâm robot đến bánh xe (m)
        
        # Chuyển đổi từ RPM sang vận tốc góc (rad/s)
        angular_velocities = [r * 2 * math.pi / 60 for r in rpm]  # RPM -> rad/s
        
        # Tính vận tốc tuyến tính của từng bánh xe (m/s)
        wheel_velocities = [w * wheel_radius for w in angular_velocities]
        
        # Mô hình động học nghịch (inverse kinematics) cho robot 3 bánh toàn hướng
        # vx = (2/3) * (v1 + v2 * cos(2π/3) + v3 * cos(4π/3))
        # vy = (2/3) * (v1 * 0 + v2 * sin(2π/3) + v3 * sin(4π/3))
        # ω = (1/(3*R)) * (v1 + v2 + v3)
        
        # Góc của các bánh xe (rad) - phụ thuộc vào cấu hình robot
        wheel_angles = [0, 2*math.pi/3, 4*math.pi/3]
        
        # Tính vận tốc robot trong hệ tọa độ robot
        vx = 0
        vy = 0
        for i in range(3):
            vx += wheel_velocities[i] * math.cos(wheel_angles[i])
            vy += wheel_velocities[i] * math.sin(wheel_angles[i])
        vx = vx * (2/3)
        vy = vy * (2/3)
        
        # Tính vận tốc góc của robot
        omega = sum(wheel_velocities) / (3 * robot_radius)
        
        # Lấy hướng hiện tại (theta) của robot
        theta = position["theta"]
        
        # Sử dụng dữ liệu IMU cho hướng nếu có
        if imu_data and "orientation" in imu_data:
            orientation = imu_data["orientation"]
            if "yaw" in orientation:
                theta = orientation["yaw"]  # Sử dụng yaw từ IMU
                position["theta"] = theta   # Cập nhật theta từ IMU
        
        # Chuyển đổi vận tốc từ hệ tọa độ robot sang hệ tọa độ thế giới
        world_vx = vx * math.cos(theta) - vy * math.sin(theta)
        world_vy = vx * math.sin(theta) + vy * math.cos(theta)
        
        # Cập nhật vị trí robot theo phương pháp Euler
        new_x = position["x"] + world_vx * delta_t
        new_y = position["y"] + world_vy * delta_t
        new_theta = position["theta"] + omega * delta_t
        
        # Giữ theta trong khoảng [-pi, pi]
        new_theta = ((new_theta + math.pi) % (2 * math.pi)) - math.pi
        
        # Cập nhật vị trí
        position["x"] = new_x
        position["y"] = new_y
        position["theta"] = new_theta
        position["last_update"] = now
        
        # Thêm điểm mới vào quỹ đạo (nếu di chuyển đủ xa)
        last_x = position["points"]["x"][-1]
        last_y = position["points"]["y"][-1]
        distance = math.sqrt((new_x - last_x)**2 + (new_y - last_y)**2)
        
        # Thêm điểm mới nếu khoảng cách > 0.05m hoặc góc thay đổi > 0.1 rad
        if distance > 0.05 or abs(new_theta - position["points"]["theta"][-1]) > 0.1:
            position["points"]["x"].append(new_x)
            position["points"]["y"].append(new_y)
            position["points"]["theta"].append(new_theta)
            
            # Giới hạn số điểm trong quỹ đạo để tránh sử dụng quá nhiều bộ nhớ
            max_points = 500
            if len(position["points"]["x"]) > max_points:
                position["points"]["x"] = position["points"]["x"][-max_points:]
                position["points"]["y"] = position["points"]["y"][-max_points:]
                position["points"]["theta"] = position["points"]["theta"][-max_points:]
        
        return position
    
    @classmethod
    def save_trajectory_to_db(cls, db: Session, robot_id: str) -> None:
        """Lưu quỹ đạo hiện tại vào database"""
        if robot_id not in cls.robot_positions:
            return
            
        position = cls.robot_positions[robot_id]
        
        # Tạo bản ghi TrajectoryData mới
        traj_data = TrajectoryData(
            robot_id=robot_id,
            current_x=position["x"],
            current_y=position["y"],
            current_theta=position["theta"],
            status="calculated",
            points=position["points"],
            timestamp=datetime.datetime.now(),
            progress_percent=100.0,  # Đã hoàn thành
            source="encoder_imu_fusion"
        )
        
        try:
            db.add(traj_data)
            db.commit()
            position["saved_points_count"] = len(position["points"]["x"])
            logger.info(f"Saved trajectory with {position['saved_points_count']} points for robot {robot_id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving trajectory for robot {robot_id}: {str(e)}")