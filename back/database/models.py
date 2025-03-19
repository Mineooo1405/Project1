from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Robot(Base):
    __tablename__ = "robots"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    motor_data = relationship("MotorData", back_populates="robot")
    pid_configs = relationship("PIDConfig", back_populates="robot")
    imu_data = relationship("IMUData", back_populates="robot")
    trajectory_data = relationship("TrajectoryData", back_populates="robot")


class MotorData(Base):
    __tablename__ = "motor_data"
    
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Tốc độ đặt của 4 động cơ
    speed1 = Column(Float)
    speed2 = Column(Float)
    speed3 = Column(Float)
    speed4 = Column(Float)
    
    # Giá trị từ encoder
    encoder1 = Column(Float, nullable=True)
    encoder2 = Column(Float, nullable=True)
    encoder3 = Column(Float, nullable=True)
    encoder4 = Column(Float, nullable=True)
    
    # Tốc độ thực đo được (RPM)
    rpm1 = Column(Float, nullable=True)
    rpm2 = Column(Float, nullable=True)
    rpm3 = Column(Float, nullable=True)
    rpm4 = Column(Float, nullable=True)
    
    command_id = Column(String, nullable=True) 
    raw_data = Column(JSON, nullable=True)  # Lưu trữ dữ liệu JSON gốc
    
    robot = relationship("Robot", back_populates="motor_data")


class PIDConfig(Base):
    __tablename__ = "pid_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"))
    motor_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    p_value = Column(Float)
    i_value = Column(Float)
    d_value = Column(Float)
    
    is_active = Column(Integer, default=1)  # 1 = config đang hoạt động
    raw_data = Column(JSON, nullable=True)  # Lưu trữ dữ liệu JSON gốc
    
    robot = relationship("Robot", back_populates="pid_configs")


class IMUData(Base):
    __tablename__ = "imu_data"
    
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Orientation
    roll = Column(Float)
    pitch = Column(Float)
    yaw = Column(Float)
    
    # Acceleration
    accel_x = Column(Float)
    accel_y = Column(Float)
    accel_z = Column(Float)
    
    # Angular velocity
    angular_vel_x = Column(Float)
    angular_vel_y = Column(Float)
    angular_vel_z = Column(Float)
    
    raw_data = Column(JSON, nullable=True)  # Lưu trữ dữ liệu JSON gốc
    
    robot = relationship("Robot", back_populates="imu_data")


class TrajectoryPoint(Base):
    __tablename__ = "trajectory_points"
    
    id = Column(Integer, primary_key=True, index=True)
    trajectory_id = Column(Integer, ForeignKey("trajectory_data.id"))
    
    x = Column(Float)
    y = Column(Float)
    theta = Column(Float, nullable=True)
    
    point_order = Column(Integer)  # Thứ tự điểm trong quỹ đạo
    
    trajectory = relationship("TrajectoryData", back_populates="points")


class TrajectoryData(Base):
    __tablename__ = "trajectory_data"
    
    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Current position
    current_x = Column(Float)
    current_y = Column(Float)
    current_theta = Column(Float)
    
    # Target position
    target_x = Column(Float)
    target_y = Column(Float)
    target_theta = Column(Float)
    
    progress_percent = Column(Float, default=0.0)
    raw_data = Column(JSON, nullable=True)  # Lưu trữ dữ liệu JSON gốc
    
    robot = relationship("Robot", back_populates="trajectory_data")
    points = relationship("TrajectoryPoint", back_populates="trajectory")