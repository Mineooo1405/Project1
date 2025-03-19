import sys
import os
import argparse
import pandas as pd
from tabulate import tabulate
from datetime import datetime, timedelta
import json
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

# Add parent directory to path to import database modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from back.database import SessionLocal, IMUData, EncoderData, MotorControl, TrajectoryData, PIDConfig

def format_timestamp(timestamp):
    """Format timestamp for display"""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp
    return timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def display_imu_data(robot_id=None, limit=10, hours=24, plot=False):
    """Display IMU data from database"""
    db = SessionLocal()
    try:
        query = db.query(IMUData)
        
        # Apply filters
        if robot_id:
            query = query.filter(IMUData.robot_id == robot_id)
        
        # Time filter
        if hours:
            since = datetime.now() - timedelta(hours=hours)
            query = query.filter(IMUData.timestamp >= since)
        
        # Get most recent records first
        query = query.order_by(IMUData.timestamp.desc())
        
        if limit:
            query = query.limit(limit)
            
        results = query.all()
        
        if not results:
            print(f"No IMU data found for robot_id={robot_id}")
            return
            
        # Display results as table
        data = []
        timestamps = []
        accel_x, accel_y, accel_z = [], [], []
        gyro_x, gyro_y, gyro_z = [], [], []
        
        for record in results:
            row = {
                "id": record.id,
                "robot_id": record.robot_id,
                "timestamp": format_timestamp(record.timestamp),
                "accel_x": round(record.accel_x, 4),
                "accel_y": round(record.accel_y, 4),
                "accel_z": round(record.accel_z, 4),
                "gyro_x": round(record.gyro_x, 4),
                "gyro_y": round(record.gyro_y, 4),
                "gyro_z": round(record.gyro_z, 4)
            }
            
            # Extract orientation if available
            if hasattr(record, 'raw_data') and record.raw_data:
                if isinstance(record.raw_data, str):
                    try:
                        raw_data = json.loads(record.raw_data)
                    except:
                        raw_data = {}
                else:
                    raw_data = record.raw_data
                    
                orientation = raw_data.get('orientation', {})
                if orientation:
                    row.update({
                        "roll": round(orientation.get('roll', 0), 4),
                        "pitch": round(orientation.get('pitch', 0), 4),
                        "yaw": round(orientation.get('yaw', 0), 4)
                    })
            
            data.append(row)
            
            # For plotting
            if plot:
                timestamps.append(record.timestamp)
                accel_x.append(record.accel_x)
                accel_y.append(record.accel_y)
                accel_z.append(record.accel_z)
                gyro_x.append(record.gyro_x)
                gyro_y.append(record.gyro_y)
                gyro_z.append(record.gyro_z)
        
        # Convert to dataframe for nice display
        df = pd.DataFrame(data)
        print(tabulate(df, headers='keys', tablefmt='pretty', showindex=False))
        print(f"Total records: {len(results)}")
        
        # Plot if requested
        if plot and timestamps:
            timestamps.reverse()
            accel_x.reverse()
            accel_y.reverse()
            accel_z.reverse()
            gyro_x.reverse()
            gyro_y.reverse()
            gyro_z.reverse()
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
            
            # Plot accelerometer data
            ax1.plot(timestamps, accel_x, label='X')
            ax1.plot(timestamps, accel_y, label='Y')
            ax1.plot(timestamps, accel_z, label='Z')
            ax1.set_title(f'Acceleration Data (Robot: {robot_id})')
            ax1.set_ylabel('Acceleration (m/s²)')
            ax1.legend()
            ax1.grid(True)
            
            # Plot gyroscope data
            ax2.plot(timestamps, gyro_x, label='X')
            ax2.plot(timestamps, gyro_y, label='Y')
            ax2.plot(timestamps, gyro_z, label='Z')
            ax2.set_title('Angular Velocity')
            ax2.set_xlabel('Time')
            ax2.set_ylabel('Angular Velocity (rad/s)')
            ax2.legend()
            ax2.grid(True)
            
            # Format time axis
            date_formatter = DateFormatter('%H:%M:%S')
            ax1.xaxis.set_major_formatter(date_formatter)
            ax2.xaxis.set_major_formatter(date_formatter)
            
            plt.tight_layout()
            plt.show()
            
    finally:
        db.close()

def display_encoder_data(robot_id=None, limit=10, hours=24, plot=False):
    """Display encoder data from database"""
    db = SessionLocal()
    try:
        query = db.query(EncoderData)
        
        # Apply filters
        if robot_id:
            query = query.filter(EncoderData.robot_id == robot_id)
        
        # Time filter
        if hours:
            since = datetime.now() - timedelta(hours=hours)
            query = query.filter(EncoderData.timestamp >= since)
        
        # Get most recent records first
        query = query.order_by(EncoderData.timestamp.desc())
        
        if limit:
            query = query.limit(limit)
            
        results = query.all()
        
        if not results:
            print(f"No encoder data found for robot_id={robot_id}")
            return
            
        # Display results as table
        data = []
        timestamps = []
        rpm_data = [[] for _ in range(3)]  # For up to 3 motors
        
        for record in results:
            row = {
                "id": record.id,
                "robot_id": record.robot_id,
                "timestamp": format_timestamp(record.timestamp),
            }
            
            # Handle values as array
            if record.values:
                for i, val in enumerate(record.values):
                    row[f"encoder{i+1}"] = val
            
            # Handle RPM as array
            if record.rpm:
                for i, val in enumerate(record.rpm):
                    row[f"rpm{i+1}"] = val
                    
                    # For plotting
                    if plot and i < 3:
                        if len(rpm_data[i]) < limit:  # Ensure we don't exceed array bounds
                            rpm_data[i].append(val)
            
            data.append(row)
            
            # For plotting
            if plot:
                timestamps.append(record.timestamp)
        
        # Convert to dataframe for nice display
        df = pd.DataFrame(data)
        print(tabulate(df, headers='keys', tablefmt='pretty', showindex=False))
        print(f"Total records: {len(results)}")
        
        # Plot if requested
        if plot and timestamps:
            timestamps.reverse()
            for i in range(len(rpm_data)):
                if rpm_data[i]:  # Only plot if we have data for this motor
                    rpm_data[i].reverse()
            
            plt.figure(figsize=(10, 6))
            
            # Plot RPM for each motor
            for i in range(len(rpm_data)):
                if rpm_data[i]:  # Only plot if we have data for this motor
                    plt.plot(timestamps, rpm_data[i], label=f'Motor {i+1}')
            
            plt.title(f'Motor RPM (Robot: {robot_id})')
            plt.xlabel('Time')
            plt.ylabel('RPM')
            plt.legend()
            plt.grid(True)
            
            # Format time axis
            date_formatter = DateFormatter('%H:%M:%S')
            plt.gca().xaxis.set_major_formatter(date_formatter)
            
            plt.tight_layout()
            plt.show()
            
    finally:
        db.close()

def display_trajectory_data(robot_id=None, limit=5, hours=24, plot=False):
    """Display trajectory data from database"""
    db = SessionLocal()
    try:
        query = db.query(TrajectoryData)
        
        # Apply filters
        if robot_id:
            query = query.filter(TrajectoryData.robot_id == robot_id)
        
        # Time filter
        if hours:
            since = datetime.now() - timedelta(hours=hours)
            query = query.filter(TrajectoryData.timestamp >= since)
        
        # Get most recent records first
        query = query.order_by(TrajectoryData.timestamp.desc())
        
        if limit:
            query = query.limit(limit)
            
        results = query.all()
        
        if not results:
            print(f"No trajectory data found for robot_id={robot_id}")
            return
            
        # Display results as table
        data = []
        
        for record in results:
            row = {
                "id": record.id,
                "robot_id": record.robot_id,
                "timestamp": format_timestamp(record.timestamp),
                "current_x": round(record.current_x, 3) if hasattr(record, 'current_x') else None,
                "current_y": round(record.current_y, 3) if hasattr(record, 'current_y') else None,
                "current_theta": round(record.current_theta, 3) if hasattr(record, 'current_theta') else None,
                "status": record.status if hasattr(record, 'status') else None,
                "points": "available" if record.points else "none"
            }
            
            data.append(row)
        
        # Convert to dataframe for nice display
        df = pd.DataFrame(data)
        print(tabulate(df, headers='keys', tablefmt='pretty', showindex=False))
        print(f"Total records: {len(results)}")
        
        # Plot if requested
        if plot and results:
            # Just plot the most recent trajectory
            record = results[0]
            if record.points and isinstance(record.points, dict):
                x_points = record.points.get('x', [])
                y_points = record.points.get('y', [])
                
                if x_points and y_points and len(x_points) == len(y_points):
                    plt.figure(figsize=(8, 8))
                    plt.plot(x_points, y_points, 'b-o', markersize=4)
                    
                    # Mark start and end points
                    if x_points and y_points:
                        plt.plot(x_points[0], y_points[0], 'go', markersize=8, label='Start')
                        plt.plot(x_points[-1], y_points[-1], 'ro', markersize=8, label='End')
                    
                    # Mark current position
                    if hasattr(record, 'current_x') and hasattr(record, 'current_y'):
                        plt.plot(record.current_x, record.current_y, 'mo', markersize=10, label='Current')
                    
                    plt.title(f'Robot Trajectory (ID: {record.robot_id})')
                    plt.xlabel('X (meters)')
                    plt.ylabel('Y (meters)')
                    plt.grid(True)
                    plt.axis('equal')  # Equal aspect ratio
                    plt.legend()
                    plt.show()
                else:
                    print("Invalid trajectory points data for plotting")
            else:
                print("No trajectory points available for plotting")
            
    finally:
        db.close()

def display_pid_config(robot_id=None, limit=10):
    """Display PID configuration from database"""
    db = SessionLocal()
    try:
        query = db.query(PIDConfig)
        
        # Apply filters
        if robot_id:
            query = query.filter(PIDConfig.robot_id == robot_id)
        
        # Get most recent records first
        query = query.order_by(PIDConfig.timestamp.desc())
        
        if limit:
            query = query.limit(limit)
            
        results = query.all()
        
        if not results:
            print(f"No PID config found for robot_id={robot_id}")
            return
            
        # Display results as table
        data = []
        
        for record in results:
            row = {
                "id": record.id,
                "robot_id": record.robot_id,
                "motor_id": record.motor_id,
                "kp": record.kp,
                "ki": record.ki,
                "kd": record.kd,
                "timestamp": format_timestamp(record.timestamp)
            }
            
            data.append(row)
        
        # Convert to dataframe for nice display
        df = pd.DataFrame(data)
        print(tabulate(df, headers='keys', tablefmt='pretty', showindex=False))
        print(f"Total records: {len(results)}")
            
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='View robot data from database')
    parser.add_argument('--type', choices=['imu', 'encoder', 'trajectory', 'pid', 'all'],
                       default='imu', help='Data type to display (default: imu)')
    parser.add_argument('--robot', help='Filter by robot ID (e.g., robot1)')
    parser.add_argument('--limit', type=int, default=10, help='Limit number of records (default: 10)')
    parser.add_argument('--hours', type=int, default=24, help='Show data from last N hours (default: 24)')
    parser.add_argument('--plot', action='store_true', help='Plot the data graphically')
    
    args = parser.parse_args()
    
    print(f"\n==== Viewing {args.type} data ====")
    print(f"Robot: {args.robot or 'all'}")
    print(f"Time range: Last {args.hours} hours")
    print(f"Limit: {args.limit} records\n")
    
    if args.type == 'all' or args.type == 'imu':
        print("\n==== IMU Data ====")
        display_imu_data(args.robot, args.limit, args.hours, args.plot)
    
    if args.type == 'all' or args.type == 'encoder':
        print("\n==== Encoder Data ====")
        display_encoder_data(args.robot, args.limit, args.hours, args.plot)
        
    if args.type == 'all' or args.type == 'trajectory':
        print("\n==== Trajectory Data ====")
        display_trajectory_data(args.robot, args.limit, args.hours, args.plot)
        
    if args.type == 'all' or args.type == 'pid':
        print("\n==== PID Configuration ====")
        display_pid_config(args.robot, args.limit)

if __name__ == "__main__":
    # Make sure we handle any missing optional dependencies
    try:
        main()
    except ImportError as e:
        missing_package = str(e).split("'")[1]
        print(f"Error: Missing required package. Please install with:\npip install {missing_package}")
    except Exception as e:
        print(f"Error: {str(e)}")