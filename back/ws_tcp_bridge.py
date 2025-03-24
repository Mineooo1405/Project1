import asyncio
import websockets
import json
import socket
import threading
import logging
import time
import os
from datetime import datetime

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(), 
        logging.FileHandler("ws_bridge.log")
    ]
)
logger = logging.getLogger("ws_bridge")

# Create logs directory
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Specific log file for PID commands verification
pid_log_file = os.path.join(log_dir, 'pid_commands.log')

def log_command(source, command_type, data):
    """Log commands for verification"""
    try:
        with open(pid_log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] SOURCE: {source}, TYPE: {command_type}\n")
            f.write(f"DATA: {json.dumps(data, indent=2)}\n\n")
        logger.info(f"Command logged: {command_type} from {source}")
    except Exception as e:
        logger.error(f"Error logging command: {e}")

# Thêm các biến để kiểm soát log
import os

# Cài đặt log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip()
LOG_HEARTBEATS = os.environ.get("LOG_HEARTBEATS", "0").strip() == "1"
LOG_DETAILED_MESSAGES = os.environ.get("LOG_DETAILED_MESSAGES", "0").strip() == "1"

# Sửa logging setup
logger = logging.getLogger("ws_tcp_bridge")
try:
    logger.setLevel(getattr(logging, LOG_LEVEL.strip()))
except AttributeError:
    logger.setLevel(logging.INFO)
    logger.warning(f"Không nhận dạng được LOG_LEVEL '{LOG_LEVEL}', sử dụng INFO thay thế")

# Hàm log có điều kiện
def conditional_log(level, message, is_heartbeat=False):
    """Ghi log có điều kiện dựa vào loại thông điệp"""
    if is_heartbeat and not LOG_HEARTBEATS:
        return
    
    if level == "INFO":
        logger.info(message)
    elif level == "WARNING":
        logger.warning(message)
    elif level == "ERROR":
        logger.error(message)
    elif level == "DEBUG":
        logger.debug(message)

# Kiểm tra nếu là thông điệp định kỳ
def is_heartbeat_message(data):
    """Kiểm tra nếu thông điệp là heartbeat hoặc get_robot_connections"""
    if isinstance(data, dict):
        message_type = data.get("type", "")
        return message_type in ["heartbeat", "get_robot_connections", "ping", "status"]
    return False

# Khai báo biến global
tcp_server_host = os.environ.get("TCP_HOST", "localhost")
tcp_server_port = int(os.environ.get("TCP_PORT", 9000))

class TCPClient:
    """Client giao tiếp với TCP server"""
    def __init__(self, host=tcp_server_host, port=tcp_server_port):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.buffer = ""
        self.lock = threading.Lock()
    
    def connect(self):
        """Kết nối đến TCP server"""
        if self.connected:
            return True
        
        try:
            with self.lock:
                logger.info(f"Đang kết nối đến TCP server ({self.host}:{self.port})...")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(5)
                self.socket.connect((self.host, self.port))
                
                # Đọc welcome message
                welcome = self.socket.recv(4096).decode('utf-8')
                logger.info(f"Đã kết nối đến TCP server: {welcome}")
                
                self.connected = True
                return True
        except Exception as e:
            logger.error(f"Không thể kết nối đến TCP server: {e}")
            return False
    
    def send_command(self, command):
        """Gửi lệnh đến TCP server và nhận phản hồi"""
        # Kiểm tra kết nối
        retry_count = 0
        max_retries = 2
        
        while not self.connected and retry_count < max_retries:
            logger.info(f"Không có kết nối TCP, thử kết nối lại (lần {retry_count+1}/{max_retries})...")
            if self.connect():
                break
            retry_count += 1
            time.sleep(1)  # Đợi 1 giây trước khi thử lại
        
        if not self.connected:
            return {
                "type": "error", 
                "status": "connection_error", 
                "message": "Không thể kết nối đến TCP server sau nhiều lần thử",
                "timestamp": time.time()
            }
        
        try:
            with self.lock:
                # Đảm bảo có robot_id
                if "robot_id" not in command and "type" in command:
                    if command["type"] != "get_robot_connections":  # Đã xử lý ở trên
                        command["robot_id"] = "robot1"  # Robot mặc định
                        logger.warning(f"Đã thêm robot_id thiếu vào lệnh {command['type']}")
                
                # Đảm bảo có timestamp
                if "timestamp" not in command:
                    command["timestamp"] = time.time()
                
                # Log command based on type
                if command.get("type") == "pid_config":
                    log_command("FRONTEND", "pid_config", command)
                elif command.get("type") == "firmware_update":
                    log_command("FRONTEND", "firmware_update", command)
                
                # Gửi lệnh đến TCP server
                message = json.dumps(command) + '\n'
                self.socket.sendall(message.encode('utf-8'))
                
                # Log tùy theo loại thông điệp
                is_heartbeat = is_heartbeat_message(command)
                if not is_heartbeat or LOG_HEARTBEATS:
                    conditional_log("INFO", f"Đã gửi đến TCP server: {command}", is_heartbeat)
                
                # Đợi phản hồi
                self.socket.settimeout(5.0)
                try:
                    # Đọc cho đến khi nhận được newline
                    data = b""
                    while '\n' not in self.buffer:
                        try:
                            chunk = self.socket.recv(4096)
                            if not chunk:
                                logger.warning("TCP server đã đóng kết nối")
                                self.connected = False
                                return {
                                    "type": "error", 
                                    "status": "connection_closed", 
                                    "message": "TCP server đã đóng kết nối",
                                    "timestamp": time.time()
                                }
                            
                            data += chunk
                            self.buffer += data.decode('utf-8')
                        except socket.error as e:
                            logger.error(f"Lỗi socket khi nhận dữ liệu: {e}")
                            self.connected = False
                            return {
                                "type": "error", 
                                "status": "socket_error", 
                                "message": f"Lỗi socket: {str(e)}",
                                "timestamp": time.time()
                            }
                    
                    # Tách thông điệp hoàn chỉnh
                    line, self.buffer = self.buffer.split('\n', 1)
                    
                    try:
                        response = json.loads(line)
                        
                        # Log response for PID or firmware
                        if command.get("type") == "pid_config" and response:
                            log_command("TCP_SERVER", "pid_response", response)
                        elif command.get("type") == "firmware_update" and response:
                            log_command("TCP_SERVER", "firmware_response", response)
                            
                        # Đảm bảo phản hồi có timestamp
                        if "timestamp" not in response:
                            response["timestamp"] = time.time()
                            
                        return response
                    except json.JSONDecodeError:
                        logger.error(f"JSON không hợp lệ trong phản hồi: {line}")
                        return {
                            "type": "error", 
                            "status": "invalid_response", 
                            "message": "Phản hồi không hợp lệ từ TCP server",
                            "timestamp": time.time()
                        }
                    
                except socket.timeout:
                    logger.warning("Không nhận được phản hồi từ TCP server (timeout)")
                    return {
                        "type": "error", 
                        "status": "timeout", 
                        "message": "TCP server không phản hồi trong thời gian chờ",
                        "timestamp": time.time()
                    }
                finally:
                    self.socket.settimeout(None)
        
        except Exception as e:
            logger.error(f"Lỗi giao tiếp với TCP server: {e}")
            self.connected = False
            return {
                "type": "error", 
                "status": "communication_error", 
                "message": f"Lỗi giao tiếp: {str(e)}",
                "timestamp": time.time()
            }
    
    def disconnect(self):
        """Đóng kết nối đến TCP server"""
        with self.lock:
            if self.socket:
                try:
                    self.socket.close()
                except Exception as e:
                    logger.error(f"Lỗi đóng kết nối TCP: {e}")
                finally:
                    self.socket = None
                    self.connected = False

# Thêm đoạn mã này sau khi định nghĩa lớp TCPClient và trước hàm handle_websocket
# Khởi tạo đối tượng TCP client global
tcp_client = TCPClient(tcp_server_host, tcp_server_port)

# Hàm kết nối lại TCP client nếu mất kết nối
def ensure_tcp_connection():
    """Đảm bảo có kết nối đến TCP server"""
    if not tcp_client.connected:
        logger.info("TCP client đang mất kết nối, thử kết nối lại...")
        return tcp_client.connect()
    return True

# Cải thiện xử lý thông điệp từ WebSocket
async def handle_websocket(websocket, path):
    """Xử lý kết nối WebSocket từ frontend"""
    logger.info("WebSocket Bridge đã kết nối")
    connection_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    logger.info(f"Kết nối mới từ {connection_id}")
    
    # Đảm bảo kết nối TCP
    ensure_tcp_connection()
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Thêm robot_id cho các lệnh get_robot_connections
                if data.get("type") == "get_robot_connections" and "robot_id" not in data:
                    data["robot_id"] = "robot1"
                    if LOG_DETAILED_MESSAGES:
                        logger.debug("Đã thêm robot_id=robot1 vào lệnh get_robot_connections")
                
                # Kiểm tra nếu là heartbeat
                is_heartbeat = is_heartbeat_message(data)
                
                # Log và gửi dữ liệu đến TCP server (có điều kiện)
                if not is_heartbeat or LOG_HEARTBEATS:
                    conditional_log("INFO", f"Nhận từ frontend: {data}", is_heartbeat)
                
                # Đảm bảo kết nối TCP còn hoạt động
                if not tcp_client.connected:
                    tcp_client.connect()
                
                # Gửi lệnh đến TCP server
                response = tcp_client.send_command(data)
                
                # Xử lý phản hồi từ TCP server (có điều kiện)
                if not is_heartbeat or LOG_HEARTBEATS:
                    conditional_log("INFO", f"Nhận từ TCP server: {response}", is_heartbeat)
                
                # Gửi phản hồi đến frontend
                await websocket.send(json.dumps(response))
                
            except json.JSONDecodeError as e:
                logger.error(f"Lỗi phân tích JSON: {e}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Định dạng JSON không hợp lệ",
                    "timestamp": time.time()
                }))
            except Exception as e:
                logger.error(f"Lỗi xử lý thông điệp: {e}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": f"Lỗi xử lý thông điệp: {str(e)}",
                    "timestamp": time.time()
                }))
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"Kết nối WebSocket từ {connection_id} đã đóng: {e}")
    except Exception as e:
        logger.error(f"Lỗi không xác định trong xử lý WebSocket: {e}")

# Thay đổi hàm main() để đọc port từ biến môi trường
async def main():
    # Đọc cấu hình từ biến môi trường hoặc sử dụng giá trị mặc định
    host = os.environ.get("WS_BRIDGE_HOST", "0.0.0.0")
    # Sử dụng port 9003 thay vì 9002
    port = int(os.environ.get("WS_BRIDGE_PORT", 9003))
    
    # Log thông tin về cấu hình
    logger.info(f"WebSocket Bridge sẽ chạy trên {host}:{port}")
    
    # Kết nối TCP client khi khởi động
    if tcp_client.connect():
        logger.info("Kết nối TCP thành công khi khởi động")
    else:
        logger.warning("Không thể kết nối TCP khi khởi động, sẽ thử lại sau")
    
    # Khởi động WebSocket server
    server = await websockets.serve(
        handle_websocket,
        host, 
        port,
        ping_interval=30,
        ping_timeout=10
    )
    
    logger.info(f"WebSocket-TCP Bridge đã khởi động trên {host}:{port}")
    await asyncio.Future()  # Chạy mãi mãi

if __name__ == "__main__":
    logger.info("Khởi động WebSocket-TCP Bridge")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Đã nhận lệnh thoát, đang đóng WebSocket-TCP Bridge...")
        # Đóng kết nối TCP khi thoát
        tcp_client.disconnect()
        logger.info("WebSocket-TCP Bridge đã đóng")
    except Exception as e:
        logger.error(f"Lỗi khi chạy WebSocket-TCP Bridge: {e}")
        # Đóng kết nối TCP khi có lỗi
        tcp_client.disconnect()