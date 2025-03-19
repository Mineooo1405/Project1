import socket
import json
import time
import random
import argparse
import datetime
import math

def send_data(host, port, robot_id, data_type, count, interval):
    """Send simulated robot data to TCP server"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        print(f"Connecting to {host}:{port}")
        s.connect((host, port))
        s.settimeout(10)  # Set a timeout to avoid hanging
        
        # Receive welcome message
        welcome = s.recv(1024).decode().strip()
        print(f"Server says: {welcome}")
        
        # Send requested number of messages
        for i in range(count):
            # Generate appropriate data based on type
            if data_type == "imu":
                data = {
                    "type": "imu_data",
                    "robot_id": robot_id,
                    "orientation": {
                        "roll": random.uniform(-0.5, 0.5),
                        "pitch": random.uniform(-0.5, 0.5),
                        "yaw": random.uniform(-3.14, 3.14)
                    },
                    "acceleration": {
                        "x": random.uniform(-0.2, 0.2),
                        "y": random.uniform(-0.2, 0.2),
                        "z": 9.8 + random.uniform(-0.1, 0.1)
                    },
                    "angular_velocity": {
                        "x": random.uniform(-0.1, 0.1),
                        "y": random.uniform(-0.1, 0.1),
                        "z": random.uniform(-0.1, 0.1)
                    },
                    "timestamp": datetime.datetime.now().isoformat()
                }
            elif data_type == "encoder":
                data = {
                    "type": "encoder_data",
                    "robot_id": robot_id,
                    "rpm": [
                        random.uniform(-30, 30),
                        random.uniform(-30, 30),
                        random.uniform(-30, 30)
                    ],
                    "timestamp": datetime.datetime.now().isoformat()
                }
            elif data_type == "motor":
                data = {
                    "type": "motor_control",
                    "robot_id": robot_id,
                    "speeds": [
                        random.uniform(-100, 100),
                        random.uniform(-100, 100),
                        random.uniform(-100, 100)
                    ],
                    "timestamp": datetime.datetime.now().isoformat()
                }
            elif data_type == "trajectory":
                # Generate a simple circular trajectory
                points_x = []
                points_y = []
                points_theta = []
                for j in range(20):
                    angle = j * 0.1
                    points_x.append(math.cos(angle))
                    points_y.append(math.sin(angle))
                    points_theta.append(angle)
                    
                data = {
                    "type": "trajectory_data",
                    "robot_id": robot_id,
                    "current_x": points_x[-1],
                    "current_y": points_y[-1],
                    "current_theta": points_theta[-1],
                    "target_x": 2.0,
                    "target_y": 0.0,
                    "target_theta": 0.0,
                    "status": "running",
                    "progress_percent": (i / count) * 100,
                    "points": {
                        "x": points_x,
                        "y": points_y,
                        "theta": points_theta
                    },
                    "timestamp": datetime.datetime.now().isoformat()
                }
            elif data_type == "pid":
                data = {
                    "type": "pid_config",
                    "robot_id": robot_id,
                    "motor_id": random.randint(1, 3),
                    "kp": 0.5 + random.uniform(-0.1, 0.1),
                    "ki": 0.2 + random.uniform(-0.05, 0.05),
                    "kd": 0.1 + random.uniform(-0.02, 0.02),
                    "timestamp": datetime.datetime.now().isoformat()
                }
            else:
                print(f"Unknown data type: {data_type}")
                return
            
            # Send the data
            json_data = json.dumps(data)
            print(f"Sending data #{i+1}/{count}: {json_data[:60]}...")
            s.sendall(json_data.encode())
            
            # Receive and print response with timeout
            try:
                response = s.recv(1024).decode()
                try:
                    response_json = json.loads(response)
                    print(f"Response: {response_json['status']} - {response_json.get('message', '')}")
                except json.JSONDecodeError:
                    print(f"Raw response: {response}")
            except socket.timeout:
                print("WARNING: Timeout waiting for server response")
                continue
            
            # Wait for the specified interval
            if i < count - 1:
                time.sleep(interval)
                
        print(f"Completed sending {count} messages of type {data_type}")

def main():
    parser = argparse.ArgumentParser(description='Send simulated robot data to TCP server')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=9000, help='Server port (default: 9000)')
    parser.add_argument('--robot', default='robot1', help='Robot ID (default: robot1)')
    parser.add_argument('--type', choices=['imu', 'encoder', 'motor', 'trajectory', 'pid'],
                        default='imu', help='Data type to send (default: imu)')
    parser.add_argument('--count', type=int, default=10, help='Number of messages to send (default: 10)')
    parser.add_argument('--interval', type=float, default=1.0, help='Interval between messages in seconds (default: 1.0)')
    
    args = parser.parse_args()
    
    try:
        send_data(args.host, args.port, args.robot, args.type, args.count, args.interval)
    except KeyboardInterrupt:
        print("Interrupted by user")
    except ConnectionRefusedError:
        print(f"Connection refused. Make sure the server is running on {args.host}:{args.port}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()