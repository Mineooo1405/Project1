from sqlalchemy import create_engine, func, desc
from sqlalchemy.orm import sessionmaker
from database import EncoderData, IMUData, MotorControl, PIDConfig, EmergencyCommand, TrajectoryData, FirmwareUpdate
from tabulate import tabulate
import datetime
import argparse
import json

# Kết nối database
DATABASE_URL = "postgresql://robot_user:140504@localhost/robot_db"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def print_section_header(title):
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)

def view_encoder_data(limit=5):
    print_section_header("ENCODER DATA")
    session = Session()
    try:
        data = session.query(EncoderData).order_by(
            desc(EncoderData.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có dữ liệu encoder trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            table_data.append([
                item.id,
                ts,
                item.values,
                item.rpm,
            ])
        
        headers = ["ID", "Timestamp", "Encoder Values", "RPM Values"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(EncoderData).count()} records")
    finally:
        session.close()

def view_imu_data(limit=5):
    print_section_header("IMU DATA")
    session = Session()
    try:
        data = session.query(IMUData).order_by(
            desc(IMUData.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có dữ liệu IMU trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            table_data.append([
                item.id,
                ts,
                item.roll,
                item.pitch,
                item.yaw,
                item.accel_x,
                item.accel_y,
                item.accel_z
            ])
        
        headers = ["ID", "Timestamp", "Roll", "Pitch", "Yaw", "Accel X", "Accel Y", "Accel Z"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(IMUData).count()} records")
    finally:
        session.close()

def view_motor_controls(limit=5):
    print_section_header("MOTOR CONTROL COMMANDS")
    session = Session()
    try:
        data = session.query(MotorControl).order_by(
            desc(MotorControl.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có lệnh điều khiển động cơ trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            table_data.append([
                item.id,
                item.command_id,
                ts,
                item.speeds
            ])
        
        headers = ["ID", "Command ID", "Timestamp", "Motor Speeds [m1,m2,m3]"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(MotorControl).count()} records")
    finally:
        session.close()

def view_pid_configs(limit=5):
    print_section_header("PID CONFIGURATIONS")
    session = Session()
    try:
        data = session.query(PIDConfig).order_by(
            desc(PIDConfig.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có cấu hình PID trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            table_data.append([
                item.id,
                item.motor_id,
                ts,
                item.p_value,
                item.i_value,
                item.d_value
            ])
        
        headers = ["ID", "Motor ID", "Timestamp", "P Value", "I Value", "D Value"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(PIDConfig).count()} records")
    finally:
        session.close()

def view_emergency_commands(limit=5):
    print_section_header("EMERGENCY STOP COMMANDS")
    session = Session()
    try:
        data = session.query(EmergencyCommand).order_by(
            desc(EmergencyCommand.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có lệnh dừng khẩn cấp trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            
            # Format raw_data
            raw_data_str = "N/A"
            if item.raw_data:
                try:
                    if isinstance(item.raw_data, dict):
                        raw_data_str = json.dumps(item.raw_data, ensure_ascii=False)[:50]
                    else:
                        raw_data_str = str(item.raw_data)[:50]
                    
                    if len(raw_data_str) >= 50:
                        raw_data_str += "..."
                except:
                    raw_data_str = "Error formatting data"
            
            table_data.append([
                item.id,
                item.command_id,
                ts,
                raw_data_str
            ])
        
        headers = ["ID", "Command ID", "Timestamp", "Raw Data"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(EmergencyCommand).count()} records")
    finally:
        session.close()

def view_trajectory_data(limit=5):
    print_section_header("TRAJECTORY DATA")
    session = Session()
    try:
        data = session.query(TrajectoryData).order_by(
            desc(TrajectoryData.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có dữ liệu quỹ đạo trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            
            # Count points
            point_count = len(item.points) if item.points else 0
            
            table_data.append([
                item.id,
                ts,
                f"({item.current_x:.2f}, {item.current_y:.2f}, {item.current_theta:.2f})",
                f"({item.target_x:.2f}, {item.target_y:.2f}, {item.target_theta:.2f})",
                f"{item.progress_percent:.1f}%",
                point_count
            ])
        
        headers = ["ID", "Timestamp", "Current (x,y,θ)", "Target (x,y,θ)", "Progress", "Points"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(TrajectoryData).count()} records")
    finally:
        session.close()

def view_firmware_updates(limit=5):
    print_section_header("FIRMWARE UPDATES")
    session = Session()
    try:
        data = session.query(FirmwareUpdate).order_by(
            desc(FirmwareUpdate.timestamp)).limit(limit).all()
        
        if not data:
            print("Không có dữ liệu cập nhật firmware trong database")
            return
        
        table_data = []
        for item in data:
            # Format timestamp nicely
            ts = item.timestamp.strftime('%Y-%m-%d %H:%M:%S') if item.timestamp else 'N/A'
            
            table_data.append([
                item.id,
                item.version,
                item.status,
                f"{item.progress}%",
                ts
            ])
        
        headers = ["ID", "Version", "Status", "Progress", "Timestamp"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {session.query(FirmwareUpdate).count()} records")
    finally:
        session.close()

def view_data_summary():
    print_section_header("DATABASE SUMMARY")
    session = Session()
    try:
        encoder_count = session.query(EncoderData).count()
        imu_count = session.query(IMUData).count()
        motor_count = session.query(MotorControl).count()
        pid_count = session.query(PIDConfig).count()
        emergency_count = session.query(EmergencyCommand).count()
        trajectory_count = session.query(TrajectoryData).count()
        firmware_count = session.query(FirmwareUpdate).count()
        
        table_data = [
            ["Encoder Data", encoder_count],
            ["IMU Data", imu_count],
            ["Motor Commands", motor_count],
            ["PID Configurations", pid_count],
            ["Emergency Commands", emergency_count],
            ["Trajectory Data", trajectory_count],
            ["Firmware Updates", firmware_count],
            ["TOTAL", encoder_count + imu_count + motor_count + pid_count + emergency_count + trajectory_count + firmware_count]
        ]
        
        headers = ["Data Type", "Record Count"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Most recent data points
        if encoder_count > 0:
            latest_encoder = session.query(EncoderData).order_by(desc(EncoderData.timestamp)).first()
            print(f"\nLatest Encoder Data: {latest_encoder.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
        if imu_count > 0:
            latest_imu = session.query(IMUData).order_by(desc(IMUData.timestamp)).first()
            print(f"Latest IMU Data: {latest_imu.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        
    finally:
        session.close()

def main():
    """Hàm chính xử lý đối số dòng lệnh và hiển thị dữ liệu"""
    parser = argparse.ArgumentParser(description="Xem kết quả test từ database")
    
    parser.add_argument("-e", "--encoder", action="store_true", help="Xem dữ liệu encoder")
    parser.add_argument("-i", "--imu", action="store_true", help="Xem dữ liệu IMU")
    parser.add_argument("-m", "--motor", action="store_true", help="Xem lệnh điều khiển động cơ")
    parser.add_argument("-p", "--pid", action="store_true", help="Xem cấu hình PID")
    parser.add_argument("-s", "--stop", action="store_true", help="Xem lệnh dừng khẩn cấp")
    parser.add_argument("-t", "--trajectory", action="store_true", help="Xem dữ liệu quỹ đạo")
    parser.add_argument("-f", "--firmware", action="store_true", help="Xem cập nhật firmware")
    parser.add_argument("-a", "--all", action="store_true", help="Xem tất cả các loại dữ liệu")
    parser.add_argument("-u", "--summary", action="store_true", help="Xem tóm tắt dữ liệu")
    parser.add_argument("-l", "--limit", type=int, default=5, help="Giới hạn số kết quả (mặc định: 5)")
    
    args = parser.parse_args()
    
    if args.summary:
        view_data_summary()
        
    if args.all or args.encoder:
        view_encoder_data(args.limit)
        
    if args.all or args.imu:
        view_imu_data(args.limit)
        
    if args.all or args.motor:
        view_motor_controls(args.limit)
        
    if args.all or args.pid:
        view_pid_configs(args.limit)
        
    if args.all or args.stop:
        view_emergency_commands(args.limit)
        
    if args.all or args.trajectory:
        view_trajectory_data(args.limit)
        
    if args.all or args.firmware:
        view_firmware_updates(args.limit)
        
    if not any([args.all, args.encoder, args.imu, args.motor, args.pid, args.stop, args.trajectory, args.firmware, args.summary]):
        parser.print_help()
        view_data_summary()

if __name__ == "__main__":
    main()