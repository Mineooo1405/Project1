from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, ARRAY
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
from sqlalchemy.dialects.postgresql import JSONB
import json
import copy
import numpy as np
import math

DATABASE_URL = "postgresql://robot_user:140504@localhost/robot_db"

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Lưu trữ file firmware
class FirmwareFile(Base):
    __tablename__ = "firmware_files"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    filename = Column(String)
    version = Column(String)
    size = Column(Integer)
    md5sum = Column(String)
    status = Column(String)  # uploaded, verified, deployed
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ metadata

# Lưu trữ thông tin cập nhật firmware
class FirmwareUpdate(Base):
    __tablename__ = "firmware_updates"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    firmware_id = Column(Integer, nullable=True)
    status = Column(String)  # pending, in_progress, completed, failed
    progress = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    completion_time = Column(DateTime, nullable=True)
    source = Column(String, nullable=True)  # Nguồn lệnh cập nhật
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ metadata

# Lưu trữ lệnh điều khiển động cơ
class MotorControl(Base):
    __tablename__ = "motor_controls"
    id = Column(Integer, primary_key=True)
    robot_id = Column(String)
    motor1_speed = Column(Float)  # RPM/Voltage/PWM
    motor2_speed = Column(Float)
    motor3_speed = Column(Float)
    timestamp = Column(DateTime)

# Lưu trữ lệnh chuyển động (x, y, theta)
class MotionCommand(Base):
    __tablename__ = "motion_commands"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    vx = Column(Float)  # Vận tốc theo x (m/s)
    vy = Column(Float)  # Vận tốc theo y (m/s)
    omega = Column(Float)  # Vận tốc góc (rad/s)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, nullable=True)  # Nguồn lệnh điều khiển
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ toàn bộ JSON message

# Lưu trữ cấu hình PID
class PIDConfig(Base):
    __tablename__ = "pid_configs"
    id = Column(Integer, primary_key=True)
    robot_id = Column(String)
    motor_id = Column(Integer)  # 1, 2, 3
    kp = Column(Float)
    ki = Column(Float)
    kd = Column(Float)
    timestamp = Column(DateTime)
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ toàn bộ JSON message

# Lưu trữ dữ liệu encoder
class EncoderData(Base):
    __tablename__ = "encoder_data"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    #values = Column(ARRAY(Float), nullable=True)
    rpm = Column(ARRAY(Float), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ toàn bộ JSON message

# Lưu trữ dữ liệu quỹ đạo
class TrajectoryData(Base):
    __tablename__ = "trajectory_data"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    # Vị trí hiện tại
    current_x = Column(Float, default=0)
    current_y = Column(Float, default=0)
    current_theta = Column(Float, default=0)
    # Thông tin tiến trình
    progress_percent = Column(Float, default=0.0)
    status = Column(String, default="idle")  # idle, pending, running, completed, aborted, error
    source = Column(String, nullable=True)   # Nguồn lệnh (webui, tcp, etc)
    # Dữ liệu quỹ đạo
    points = Column(JSONB, nullable=True)  # Mảng các điểm [{x, y, theta}, ...]
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ toàn bộ JSON message

# Lưu trữ dữ liệu IMU
class IMUData(Base):
    __tablename__ = "imu_data"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    accel_x = Column(Float, default=0)
    accel_y = Column(Float, default=0)
    accel_z = Column(Float, default=0)
    gyro_x = Column(Float, default=0)
    gyro_y = Column(Float, default=0)
    gyro_z = Column(Float, default=0)
    mag_x = Column(Float, default=0, nullable=True)
    mag_y = Column(Float, default=0, nullable=True)
    mag_z = Column(Float, default=0, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ toàn bộ JSON message

# Lưu trữ lệnh khẩn cấp
class EmergencyCommand(Base):
    __tablename__ = "emergency_commands"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    command_type = Column(String)  # STOP, RESUME, etc.
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, nullable=True)  # Nguồn lệnh
    raw_data = Column(JSONB, nullable=True)  # Lưu trữ toàn bộ JSON message

# Lưu trữ nhật ký kết nối
class ConnectionLog(Base):
    __tablename__ = "connection_logs"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String)  # 'connected', 'disconnected', 'error'
    client_ip = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    details = Column(JSONB)  # Chi tiết bổ sung

# Add this with your other model definitions

class CommandLog(Base):
    __tablename__ = "command_logs"
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(String, default="robot1")
    command_type = Column(String)  # motor, trajectory, pid, firmware, etc.
    command_data = Column(JSONB)   # Dữ liệu lệnh đầy đủ
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, nullable=True)  # Nguồn lệnh

# Tạo class tiện ích để xử lý dữ liệu JSON
class JSONDataHandler:
    @staticmethod
    def store_json_message(db, json_data):
        """Lưu trữ tin nhắn JSON vào bảng thích hợp dựa vào loại tin nhắn"""
        if not isinstance(json_data, dict):
            try:
                import json
                json_data = json.loads(json_data)
            except Exception as e:
                print(f"Lỗi phân tích JSON: {e}")
                return None

        msg_type = json_data.get("type")
        timestamp = datetime.datetime.fromtimestamp(
            json_data.get("timestamp", datetime.datetime.utcnow().timestamp())
        )

        if msg_type == "motor_control":
            # Xử lý lệnh điều khiển động cơ
            speeds = json_data.get("speeds", [0, 0, 0])
            motor_control = MotorControl(
                command_id=json_data.get("command_id", ""),
                speeds=speeds,
                timestamp=timestamp,
                raw_data=json_data
            )
            db.add(motor_control)
            db.commit()
            return motor_control

        elif msg_type == "motion_command":
            # Xử lý lệnh chuyển động
            velocities = json_data.get("velocities", {})
            motion_cmd = MotionCommand(
                command_id=json_data.get("command_id", ""),
                velocity_x=velocities.get("x", 0),
                velocity_y=velocities.get("y", 0),
                velocity_theta=velocities.get("theta", 0),
                timestamp=timestamp,
                raw_data=json_data
            )
            db.add(motion_cmd)
            db.commit()
            return motion_cmd

        elif msg_type == "pid_update":
            # Xử lý cập nhật PID
            params = json_data.get("parameters", {})
            pid_config = PIDConfig(
                motor_id=json_data.get("motor_id", 0),
                p_value=params.get("p", 0),
                i_value=params.get("i", 0),
                d_value=params.get("d", 0),
                timestamp=timestamp,
                raw_data=json_data
            )
            db.add(pid_config)
            db.commit()
            return pid_config

        elif msg_type == "encoder_data":
            # Xử lý dữ liệu encoder
            values = json_data.get("values", [0, 0, 0])
            rpm = json_data.get("rpm", [0, 0, 0])
            encoder_data = EncoderData(
                values=values,
                rpm=rpm,
                timestamp=timestamp, 
                raw_data=json_data
            )
            db.add(encoder_data)
            db.commit()
            return encoder_data

        elif msg_type == "trajectory_data":
            # Xử lý dữ liệu quỹ đạo
            current = json_data.get("current_position", {})
            # Removed references to target position
            progress = json_data.get("progress_percent", 0)
            points = json_data.get("points", [])
            
            traj_data = TrajectoryData(
                current_x=current.get("x", 0),
                current_y=current.get("y", 0),
                current_theta=current.get("theta", 0),
                # Target fields removed
                progress_percent=progress,
                points=points,
                timestamp=timestamp,
                raw_data=json_data  # Vẫn lưu raw data có thể chứa thông tin target
            )
            db.add(traj_data)
            db.commit()
            return traj_data

        elif msg_type == "imu_data":
            # Xử lý dữ liệu IMU
            orientation = json_data.get("orientation", {})
            accel = json_data.get("acceleration", {})
            ang_vel = json_data.get("angular_velocity", {})
            
            imu_data = IMUData(
                roll=orientation.get("roll", 0),
                pitch=orientation.get("pitch", 0),
                yaw=orientation.get("yaw", 0),
                accel_x=accel.get("x", 0),
                accel_y=accel.get("y", 0),
                accel_z=accel.get("z", 0),
                ang_vel_x=ang_vel.get("x", 0),
                ang_vel_y=ang_vel.get("y", 0),
                ang_vel_z=ang_vel.get("z", 0),
                timestamp=timestamp,
                raw_data=json_data
            )
            db.add(imu_data)
            db.commit()
            return imu_data

        elif msg_type == "firmware_status":
            # Xử lý cập nhật firmware
            status = json_data.get("status", "")
            progress = json_data.get("progress", 0)
            version = json_data.get("version", "")
            
            firmware_update = FirmwareUpdate(
                version=version,
                status=status,
                progress=progress,
                timestamp=timestamp,
                raw_data=json_data
            )
            db.add(firmware_update)
            db.commit()
            return firmware_update

        elif msg_type == "emergency_stop":
            # Xử lý lệnh khẩn cấp
            emergency = EmergencyCommand(
                command_id=json_data.get("command_id", ""),
                timestamp=timestamp,
                raw_data=json_data
            )
            db.add(emergency)
            db.commit()
            return emergency

        else:
            print(f"Không hỗ trợ loại tin nhắn: {msg_type}")
            return None

    @staticmethod
    def process_dict(data):
        """Process dictionary to make it JSON serializable"""
        if data is None:
            return {}
        
        # Deep copy to avoid modifying original
        result = copy.deepcopy(data)
        
        # Process each key to ensure serializability
        for key in list(result.keys()):
            if isinstance(result[key], (datetime.datetime, datetime.date)):
                # Convert datetime to ISO string
                result[key] = result[key].isoformat()
            elif isinstance(result[key], (set, complex)):
                # Convert set to list and complex to string
                result[key] = str(result[key])
            elif callable(result[key]):
                # Convert function to string representation
                result[key] = str(result[key])
            elif isinstance(result[key], dict):
                # Recursively process nested dictionaries
                result[key] = JSONDataHandler.process_dict(result[key])
            elif isinstance(result[key], list):
                # Process lists
                for i, item in enumerate(result[key]):
                    if isinstance(item, dict):
                        result[key][i] = JSONDataHandler.process_dict(item)
        
        return result

class TrajectoryCalculator:
    # Thông số robot
    WHEEL_RADIUS = 0.03  # Bán kính bánh xe (m)
    ROBOT_RADIUS = 0.153  # Bán kính robot (m)
    DT = 0.05  # Thời gian lấy mẫu (s)

    @staticmethod
    def compute_velocity(theta, omega_wheel):
        """
        Tính vận tốc robot từ vận tốc góc của các bánh xe
        
        Parameters:
        -----------
        theta : float
            Góc quay hiện tại của robot (rad)
        omega_wheel : array_like
            Mảng vận tốc góc của 3 bánh xe (rad/s)
            
        Returns:
        --------
        tuple
            (vx, vy, omega) - vận tốc dài và vận tốc góc của robot
        """
        # Ma trận động học ngược
        H = np.array([
            [-np.sin(theta), np.cos(theta), TrajectoryCalculator.ROBOT_RADIUS],
            [-np.sin(np.pi/3 - theta), -np.cos(np.pi/3 - theta), TrajectoryCalculator.ROBOT_RADIUS],
            [np.sin(np.pi/3 + theta), -np.cos(np.pi/3 + theta), TrajectoryCalculator.ROBOT_RADIUS]
        ])
        
        # Nhân với bán kính bánh xe
        omega_scaled = np.array(omega_wheel) * TrajectoryCalculator.WHEEL_RADIUS
        
        # Giải phương trình động học để tìm vận tốc
        try:
            velocities = np.linalg.solve(H, omega_scaled)
            return velocities[0], velocities[1], velocities[2]
        except np.linalg.LinAlgError:
            # Xử lý khi ma trận không khả nghịch
            print("Lỗi: Ma trận động học không khả nghịch")
            return 0, 0, 0
    
    @staticmethod
    def rpm_to_trajectory(rpm_data, initial_position=(0, 0, 0)):
        """
        Chuyển đổi từ dữ liệu RPM sang quỹ đạo robot
        
        Parameters:
        -----------
        rpm_data : list of tuples
            Danh sách các bộ 3 giá trị RPM của 3 bánh xe
        initial_position : tuple
            (x, y, theta) - vị trí ban đầu của robot
            
        Returns:
        --------
        dict
            Dictionary chứa quỹ đạo robot dạng {'x': [...], 'y': [...], 'theta': [...]}
        """
        # Vị trí ban đầu
        x, y, theta = initial_position
        
        # Quỹ đạo
        x_hist = [x]
        y_hist = [y]
        theta_hist = [theta]
        
        # Lặp qua từng dữ liệu RPM
        for rpm in rpm_data:
            # Chuyển RPM sang rad/s
            omega_wheel = [r * (2 * np.pi / 60) for r in rpm]
            
            # Tính vận tốc
            v_x, v_y, omega = TrajectoryCalculator.compute_velocity(theta, omega_wheel)
            
            # Cập nhật vị trí bằng tích phân Euler
            x += v_x * TrajectoryCalculator.DT
            y += v_y * TrajectoryCalculator.DT
            theta += omega * TrajectoryCalculator.DT
            
            # Giữ theta trong khoảng [-pi, pi]
            theta = math.atan2(math.sin(theta), math.cos(theta))
            
            # Lưu vị trí
            x_hist.append(x)
            y_hist.append(y)
            theta_hist.append(theta)
        
        return {
            'x': x_hist,
            'y': y_hist,
            'theta': theta_hist
        }
    
    @staticmethod
    def process_encoder_data(db, robot_id, start_time=None, end_time=None):
        """
        Xử lý dữ liệu encoder từ database và tính toán quỹ đạo
        """
        # Truy vấn dữ liệu encoder từ database
        query = db.query(EncoderData).filter(EncoderData.robot_id == robot_id)
        
        if start_time:
            query = query.filter(EncoderData.timestamp >= start_time)
        if end_time:
            query = query.filter(EncoderData.timestamp <= end_time)
            
        # Sắp xếp theo thời gian
        query = query.order_by(EncoderData.timestamp)
        
        encoder_data = query.all()
        
        # Lấy giá trị RPM từ các record
        rpm_data = [ed.rpm for ed in encoder_data]
        
        # Tính quỹ đạo
        if rpm_data:
            trajectory = TrajectoryCalculator.rpm_to_trajectory(rpm_data)
            
            # Tạo một trajectory data mới
            traj_data = TrajectoryData(
                robot_id=robot_id,
                current_x=trajectory['x'][-1] if trajectory['x'] else 0,
                current_y=trajectory['y'][-1] if trajectory['y'] else 0,
                current_theta=trajectory['theta'][-1] if trajectory['theta'] else 0,
                status="calculated",
                points={
                    'x': trajectory['x'],
                    'y': trajectory['y'],
                    'theta': trajectory['theta']
                },
                timestamp=datetime.datetime.utcnow(),
                raw_data={'source': 'encoder_data', 'points_count': len(trajectory['x'])}
            )
            
            db.add(traj_data)
            db.commit()
            
            return trajectory
        
        return {'x': [], 'y': [], 'theta': []}

# Tạo tất cả bảng trong database
Base.metadata.create_all(bind=engine)
