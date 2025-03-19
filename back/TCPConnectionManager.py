import socket
import threading
import json
import time
from sqlalchemy.orm import Session
from database import SessionLocal, EncoderData, IMUData, JSONDataHandler
import re
import asyncio

class TCPConnectionManager:
    def __init__(self, host="0.0.0.0", port=5005):
        self.server_host = host
        self.server_port = port
        self.robot_connections = {}  # {robot_id: socket}
        self.lock = threading.Lock()
        self.running = True
        
    def save_to_database(self, robot_id, data_str):
        """Lưu dữ liệu từ ESP32 vào database"""
        try:
            db = SessionLocal()
            
            # Phân tích dữ liệu từ ESP32
            if data_str.startswith("1:"):  # Định dạng RPM
                pattern = r"(\d):(-?\d+(?:\.\d+)?)"
                matches = re.findall(pattern, data_str)
                
                # Tạo dữ liệu encoder
                values = [0, 0, 0]
                rpm = [0, 0, 0]
                
                for motor_id, value in matches:
                    motor_idx = int(motor_id) - 1
                    if 0 <= motor_idx < 3:
                        values[motor_idx] = int(float(value)) if value else 0
                        rpm[motor_idx] = float(value) if value else 0
                
                encoder_entry = EncoderData(
                    values=values,
                    rpm=rpm
                )
                db.add(encoder_entry)
                    
            elif data_str.startswith("IMU:"):  # Định dạng IMU data
                # Giả sử dữ liệu có dạng "IMU:theta=1.2,omega=[10,20,30],x=5,y=10"
                data = data_str.replace("IMU:", "").strip()
                parts = data.split(",")
                imu_data = {}
                
                for part in parts:
                    key, value = part.split("=")
                    if key == "omega":
                        value = json.loads(value)
                    else:
                        value = float(value)
                    imu_data[key] = value
                
                imu_entry = IMUData(
                    yaw=imu_data.get("theta", 0),
                    # Lưu omega trong raw_data
                    raw_data={"omega": imu_data.get("omega", [0, 0, 0])},
                    accel_x=imu_data.get("x", 0) * 100,  # Chuyển đổi đơn vị nếu cần
                    accel_y=imu_data.get("y", 0) * 100,
                    # Các giá trị khác cần thiết cho IMUData
                    roll=0.0,
                    pitch=0.0,
                    accel_z=0.0,
                    ang_vel_x=0.0,
                    ang_vel_y=0.0,
                    ang_vel_z=0.0
                )
                db.add(imu_entry)
                
            db.commit()
            
            # Phát sóng dữ liệu đến tất cả websocket clients
            from main import broadcast_trajectory
            import asyncio
            asyncio.run_coroutine_threadsafe(broadcast_trajectory(), asyncio.get_event_loop())
            
        except Exception as e:
            print(f"Lỗi khi lưu dữ liệu: {e}")
        finally:
            db.close()
    
    def handle_client(self, client_socket):
        """Xử lý kết nối từ ESP32"""
        print("Đang xử lý kết nối mới...")
        try:
            # Nhận robot_id từ ESP32
            robot_id_data = client_socket.recv(1024).decode().strip()
            if not robot_id_data:
                print("Client không gửi ID, ngắt kết nối")
                client_socket.close()
                return
            
            # Giả sử format "ID:{robot_id}"
            robot_id = robot_id_data
            if robot_id_data.startswith("ID:"):
                robot_id = robot_id_data[3:]
            
            print(f"Robot {robot_id} đã kết nối")
            
            # Lưu kết nối vào dictionary
            with self.lock:
                # Đóng kết nối cũ nếu có
                if robot_id in self.robot_connections:
                    try:
                        self.robot_connections[robot_id].close()
                    except:
                        pass
                self.robot_connections[robot_id] = client_socket
            
            # Nhận dữ liệu liên tục từ ESP32
            buffer = ""
            while self.running:
                try:
                    data = client_socket.recv(1024).decode()
                    if not data:
                        break
                    
                    buffer += data
                    
                    # Xử lý dữ liệu theo từng dòng
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            print(f"Nhận từ {robot_id}: {line}")
                            self.save_to_database(robot_id, line)
                
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Lỗi khi nhận dữ liệu từ {robot_id}: {e}")
                    break
        except Exception as e:
            print(f"Lỗi xử lý client: {e}")
        finally:
            # Đóng kết nối và xóa khỏi dictionary
            with self.lock:
                for rid, sock in list(self.robot_connections.items()):
                    if sock == client_socket:
                        del self.robot_connections[rid]
                        break
            client_socket.close()
    
    def start(self):
        """Khởi động TCP server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.server_host, self.server_port))
        server.listen(10)
        print(f"TCP Server đang chạy trên {self.server_host}:{self.server_port}...")
        
        while self.running:
            try:
                client_socket, addr = server.accept()
                print(f"Kết nối mới từ {addr}")
                
                client_handler = threading.Thread(target=self.handle_client, args=(client_socket,))
                client_handler.daemon = True
                client_handler.start()
                
            except Exception as e:
                print(f"Lỗi khi chấp nhận kết nối: {e}")
                if not self.running:
                    break
        
        server.close()
        print("TCP Server đã dừng.")
    
    def send_command(self, robot_id, command):
        """Gửi lệnh đến ESP32 cụ thể"""
        with self.lock:
            if robot_id not in self.robot_connections:
                return f"Robot {robot_id} không được kết nối"
            
            try:
                sock = self.robot_connections[robot_id]
                sock.sendall(f"{command}\n".encode())
                return f"Đã gửi '{command}' đến {robot_id}"
            except Exception as e:
                return f"Lỗi gửi lệnh đến {robot_id}: {e}"
    
    def stop(self):
        """Dừng TCP server"""
        self.running = False
        with self.lock:
            for sock in self.robot_connections.values():
                try:
                    sock.close()
                except:
                    pass
            self.robot_connections.clear()

    def process_robot_message(self, message, client_id):
        """Process incoming messages from robot and store in database"""
        try:
            data = json.loads(message)
            
            # Store the message using JSONDataHandler
            db = SessionLocal()
            try:
                result = JSONDataHandler.store_json_message(db, data)
            finally:
                db.close()
            
            # Handle specific message types
            msg_type = data.get("type")
            if msg_type == "encoder_data":
                # Create task to broadcast updated data to clients
                from main import broadcast_motor_data
                import asyncio
                asyncio.run_coroutine_threadsafe(broadcast_motor_data(), asyncio.get_event_loop())
            elif msg_type == "trajectory_data":
                # Create task to broadcast updated trajectory
                from main import broadcast_trajectory
                import asyncio
                asyncio.run_coroutine_threadsafe(broadcast_trajectory(), asyncio.get_event_loop())
            elif msg_type == "imu_data":
                # Update any UI that needs IMU data
                pass
                
        except json.JSONDecodeError:
            print(f"Received invalid JSON from {client_id}: {message[:100]}")
        except Exception as e:
            print(f"Error processing robot message: {e}")

    def is_robot_connected(self, robot_id: str) -> bool:
        """
        Check if a specific robot is connected to the TCP server
        
        Args:
            robot_id: The ID of the robot to check
            
        Returns:
            bool: True if robot is connected, False otherwise
        """
        try:
            # Điều chỉnh logic này cho phù hợp với cách bạn quản lý kết nối
            # Lấy robot ID number từ tên
            if robot_id.startswith("robot"):
                robot_number = robot_id[5:]  # "robot1" -> "1"
            else:
                robot_number = robot_id
                
            # Kiểm tra trong danh sách kết nối
            # Thay thế bằng cách bạn lưu trữ thực tế trong lớp này
            if hasattr(self, "clients"):
                return robot_number in self.clients
            elif hasattr(self, "connections"):
                return robot_number in self.connections
            elif hasattr(self, "active_connections"):
                return robot_number in self.active_connections
            elif hasattr(self, "robot_connections"):
                return robot_number in self.robot_connections
            else:
                # Fallback: luôn trả về False nếu không tìm thấy cách xác định kết nối
                return False
        except Exception as e:
            print(f"Error in is_robot_connected: {e}")
            return False