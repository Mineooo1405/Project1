import psycopg2
import json
from tabulate import tabulate
from datetime import datetime
import sys
import argparse
from sqlalchemy import create_engine, func, desc
from sqlalchemy.orm import sessionmaker
from database import EncoderData, IMUData, MotorControl, PIDConfig, EmergencyCommand, TrajectoryData
from database import JSONDataHandler

# Kết nối database
DATABASE_URL = "postgresql://robot_user:140504@localhost/robot_db"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def get_encoder_data(limit=10):
    """Lấy dữ liệu encoder mới nhất từ database"""
    session = Session()
    try:
        data = session.query(EncoderData).order_by(
            desc(EncoderData.timestamp)).limit(limit).all()
        
        table_data = []
        for item in data:
            table_data.append([
                item.id,
                item.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                item.values if item.values else [],
                item.rpm if item.rpm else []
            ])
        
        headers = ["ID", "Timestamp", "Values", "RPM"]
        print("\n=== Encoder Data ===")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    finally:
        session.close()

def get_imu_data(limit=10):
    """Lấy dữ liệu IMU mới nhất từ database"""
    session = Session()
    try:
        data = session.query(IMUData).order_by(
            desc(IMUData.timestamp)).limit(limit).all()
        
        table_data = []
        for item in data:
            table_data.append([
                item.id,
                item.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                item.roll,
                item.pitch,
                item.yaw,
                item.accel_x,
                item.accel_y,
                item.accel_z
            ])
        
        headers = ["ID", "Timestamp", "Roll", "Pitch", "Yaw", "Accel X", "Accel Y", "Accel Z"]
        print("\n=== IMU Data ===")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    finally:
        session.close()

def get_motor_commands(limit=10):
    """Lấy các lệnh điều khiển động cơ mới nhất từ database"""
    session = Session()
    try:
        data = session.query(MotorControl).order_by(
            desc(MotorControl.timestamp)).limit(limit).all()
        
        table_data = []
        for item in data:
            table_data.append([
                item.id,
                item.command_id,
                item.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                item.speeds if item.speeds else []
            ])
        
        headers = ["ID", "Command ID", "Timestamp", "Speeds"]
        print("\n=== Motor Commands ===")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    finally:
        session.close()

def get_pid_configs(limit=10):
    """Lấy cấu hình PID mới nhất từ database"""
    session = Session()
    try:
        data = session.query(PIDConfig).order_by(
            desc(PIDConfig.timestamp)).limit(limit).all()
        
        table_data = []
        for item in data:
            table_data.append([
                item.id,
                item.motor_id,
                item.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                item.p_value,
                item.i_value,
                item.d_value
            ])
        
        headers = ["ID", "Motor ID", "Timestamp", "P", "I", "D"]
        print("\n=== PID Configurations ===")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    finally:
        session.close()

def get_emergency_commands(limit=10):
    """Lấy lệnh khẩn cấp mới nhất từ database"""
    session = Session()
    try:
        data = session.query(EmergencyCommand).order_by(
            desc(EmergencyCommand.timestamp)).limit(limit).all()
        
        table_data = []
        for item in data:
            table_data.append([
                item.id,
                item.command_id,
                item.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                json.dumps(item.raw_data)[:50] + "..." if item.raw_data else "N/A"
            ])
        
        headers = ["ID", "Command ID", "Timestamp", "Raw Data"]
        print("\n=== Emergency Commands ===")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    finally:
        session.close()

def get_trajectory_data(limit=10):
    """Lấy dữ liệu quỹ đạo mới nhất từ database"""
    session = Session()
    try:
        data = session.query(TrajectoryData).order_by(
            desc(TrajectoryData.timestamp)).limit(limit).all()
        
        table_data = []
        for item in data:
            table_data.append([
                item.id,
                item.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                item.current_x,
                item.current_y,
                item.current_theta,
                item.target_x,
                item.target_y,
                item.target_theta,
                item.progress_percent,
                f"{len(item.points) if item.points else 0} points"
            ])
        
        headers = ["ID", "Timestamp", "Curr X", "Curr Y", "Curr θ", 
                   "Targ X", "Targ Y", "Targ θ", "Progress", "Points"]
        print("\n=== Trajectory Data ===")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
    finally:
        session.close()

def generate_test_data():
    """Tạo dữ liệu test để lưu vào database"""
    session = Session()
    try:
        print("Đang tạo dữ liệu test...")
        
        # 1. Tạo dữ liệu encoder
        encoder_data = {
            "type": "encoder_data",
            "timestamp": datetime.now().timestamp(),
            "values": [1024, 980, 1043],
            "rpm": [120.5, 115.2, 122.6]
        }
        
        # 2. Tạo dữ liệu IMU
        imu_data = {
            "type": "imu_data",
            "timestamp": datetime.now().timestamp(),
            "orientation": {
                "roll": 1.24,
                "pitch": 0.05,
                "yaw": 45.7
            },
            "acceleration": {
                "x": 0.23,
                "y": 0.11,
                "z": 9.81
            },
            "angular_velocity": {
                "x": 0.01,
                "y": 0.02,
                "z": 0.05
            }
        }
        
        # 3. Tạo lệnh điều khiển động cơ
        motor_data = {
            "type": "motor_control",
            "speeds": [50, -30, 50],
            "timestamp": datetime.now().timestamp(),
            "command_id": f"cmd_{int(datetime.now().timestamp()*1000)}"
        }
        
        # 4. Tạo dữ liệu PID
        pid_data = {
            "type": "pid_update",
            "parameters": {
                "p": 0.7,
                "i": 0.3,
                "d": 0.15
            },
            "motor_id": 1,
            "timestamp": datetime.now().timestamp()
        }
        
        # 5. Tạo lệnh dừng khẩn cấp
        emergency_data = {
            "type": "emergency_stop",
            "timestamp": datetime.now().timestamp(),
            "command_id": f"stop_{int(datetime.now().timestamp()*1000)}"
        }
        
        # 6. Tạo dữ liệu quỹ đạo
        trajectory_data = {
            "type": "trajectory_data",
            "points": [
                {"x": 10.0, "y": 5.0, "theta": 0.0},
                {"x": 11.0, "y": 5.5, "theta": 0.1},
                {"x": 12.0, "y": 6.0, "theta": 0.2}
            ],
            "current_position": {"x": 10.0, "y": 5.0, "theta": 0.0},
            "target_position": {"x": 20.0, "y": 15.0, "theta": 1.57},
            "progress_percent": 0.0,
            "timestamp": datetime.now().timestamp()
        }
        
        # Lưu dữ liệu vào database bằng JSONDataHandler
        for data in [encoder_data, imu_data, motor_data, pid_data, emergency_data, trajectory_data]:
            JSONDataHandler.store_json_message(session, data)
            
        session.commit()
        print("Đã lưu dữ liệu test vào database!")
        
    except Exception as e:
        session.rollback()
        print(f"Lỗi khi tạo dữ liệu test: {e}")
    finally:
        session.close()

def test_websocket_connection():
    """Test kết nối WebSocket để gửi và nhận dữ liệu"""
    import websockets
    import asyncio
    
    async def connect_and_send():
        uri = "ws://localhost:8000/ws"
        async with websockets.connect(uri) as websocket:
            # Gửi lệnh PID
            pid_data = {
                "type": "pid_control",
                "robot_id": "test_robot",
                "motor_id": 2,
                "parameters": {
                    "p": 0.75,
                    "i": 0.25,
                    "d": 0.1
                }
            }
            
            print(f"Gửi: {json.dumps(pid_data)}")
            await websocket.send(json.dumps(pid_data))
            
            # Đợi phản hồi
            response = await websocket.recv()
            print(f"Nhận: {response}")
            
            # Gửi lệnh điều khiển động cơ
            motor_cmd = {
                "type": "motor_control",
                "robot_id": "test_robot",
                "speeds": [40, 30, 20]
            }
            
            print(f"Gửi: {json.dumps(motor_cmd)}")
            await websocket.send(json.dumps(motor_cmd))
            
            # Đợi phản hồi
            response = await websocket.recv()
            print(f"Nhận: {response}")
            
    asyncio.run(connect_and_send())

def main():
    """Hàm chính xử lý đối số dòng lệnh và thực hiện các hoạt động"""
    parser = argparse.ArgumentParser(description="Công cụ kiểm tra và tạo dữ liệu test cho WebDashboard")
    
    parser.add_argument("-e", "--encoder", action="store_true", help="Xem dữ liệu encoder")
    parser.add_argument("-i", "--imu", action="store_true", help="Xem dữ liệu IMU")
    parser.add_argument("-m", "--motor", action="store_true", help="Xem lệnh điều khiển động cơ")
    parser.add_argument("-p", "--pid", action="store_true", help="Xem cấu hình PID")
    parser.add_argument("-s", "--stop", action="store_true", help="Xem lệnh dừng khẩn cấp")
    parser.add_argument("-t", "--trajectory", action="store_true", help="Xem dữ liệu quỹ đạo")
    parser.add_argument("-g", "--generate", action="store_true", help="Tạo dữ liệu test")
    parser.add_argument("-w", "--websocket", action="store_true", help="Test kết nối WebSocket")
    parser.add_argument("-a", "--all", action="store_true", help="Xem toàn bộ dữ liệu")
    parser.add_argument("-l", "--limit", type=int, default=10, help="Giới hạn số kết quả (mặc định: 10)")
    
    args = parser.parse_args()
    
    if args.generate:
        generate_test_data()
        return
        
    if args.websocket:
        test_websocket_connection()
        return
    
    if args.all or args.encoder:
        get_encoder_data(args.limit)
        
    if args.all or args.imu:
        get_imu_data(args.limit)
        
    if args.all or args.motor:
        get_motor_commands(args.limit)
        
    if args.all or args.pid:
        get_pid_configs(args.limit)
        
    if args.all or args.stop:
        get_emergency_commands(args.limit)
        
    if args.all or args.trajectory:
        get_trajectory_data(args.limit)
        
    if not any([args.all, args.encoder, args.imu, args.motor, args.pid, args.stop, args.trajectory, args.generate, args.websocket]):
        parser.print_help()

if __name__ == "__main__":
    main()