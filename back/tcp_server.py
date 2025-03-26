import socket
import threading
import json
import asyncio
import websockets
import logging
import time
import sys
import os
import random
from datetime import datetime
import traceback
ENABLE_BACKEND_CONNECTION = True
robots = {}  # robot_id -> websocket
robot_data = {}  # robot_id -> registration data
tcp_robots = {}  # robot_id -> (reader, writer)

# Import cấu hình
from config import (
    TCP_SERVER_HOST, TCP_SERVER_PORT,
    BACKEND_HOST, BACKEND_PORT,
    API_KEY, LOG_LEVEL, LOG_FILE, DEBUG
)

# Cấu hình logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger("tcp_server")

# Thêm các biến để kiểm soát log
import os

# Cài đặt log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip()
LOG_HEARTBEATS = os.environ.get("LOG_HEARTBEATS", "0").strip() == "1" 
LOG_DETAILED_MESSAGES = os.environ.get("LOG_DETAILED_MESSAGES", "0").strip() == "1"
DEBUG_MODE = os.environ.get("DEBUG_MODE", "0").strip() == "1"

# Khởi tạo thời gian bắt đầu server
start_time = time.time()

# Sửa logging setup
logger = logging.getLogger("tcp_server")
try:
    level_name = LOG_LEVEL.strip()
    logger.setLevel(getattr(logging, level_name))
except (AttributeError, ValueError):
    logger.setLevel(logging.INFO)
    logger.warning(f"Không nhận dạng được LOG_LEVEL '{LOG_LEVEL}', sử dụng INFO thay thế")

# Hàm log có điều kiện
def conditional_log(level, message, is_heartbeat=False):
    """Ghi log có điều kiện dựa ando loại thông điệp"""
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

# Khai báo biến toàn cục
robots = {}  # {robot_id: socket}
backend_connections = {}  # {robot_id: websocket}
frontend_bridge = None  # WebSocket connection to frontend bridge
clients = {}  # {client_id: socket}
clients_lock = threading.Lock()
robots_lock = threading.Lock()
robot_data = {}  # Lưu trữ dữ liệu robot: {robot_id: {data}}
bridge_connections = {}  # {robot_id: websocket}

# === BACKEND CONNECTION MANAGEMENT ===

# Add WebSocket connection to frontend bridge
async def connect_to_ws_bridge():
    """Connect to WebSocket Bridge to send/receive frontend messages"""
    global frontend_bridge
    
    uri = f"ws://localhost:9003/tcp_server"
    try:
        websocket = await websockets.connect(uri)
        logger.info(f"Connected to WebSocket Bridge at {uri}")
        
        # Set as frontend bridge
        frontend_bridge = websocket
        
        # Send identification
        await websocket.send(json.dumps({
            "type": "server_connection",
            "source": "tcp_server",
            "timestamp": time.time()
        }))
        
        # Start message handler
        asyncio.create_task(handle_ws_bridge_messages(websocket))
        
        return True
    except Exception as e:
        logger.error(f"Failed to connect to WebSocket Bridge: {e}")
        return False

async def handle_ws_bridge_messages(websocket):
    """Handle messages from WebSocket Bridge"""
    global frontend_bridge
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"[WS] Received from WebSocket Bridge: {data.get('type')}")
                
                # Handle frontend messages and forward to appropriate robot
                robot_id = data.get("robot_id")
                if robot_id and robot_id in tcp_robots:
                    # Forward message to TCP robot
                    try:
                        _, writer = tcp_robots[robot_id]
                        writer.write((json.dumps(data) + '\n').encode('utf-8'))
                        await writer.drain()
                        logger.info(f"[WS] Forwarded message to robot {robot_id}")
                        
                        # Send acknowledgment back to frontend
                        await websocket.send(json.dumps({
                            "type": "command_sent",
                            "robot_id": robot_id,
                            "original_type": data.get("type"),
                            "timestamp": time.time()
                        }))
                    except Exception as e:
                        logger.error(f"[WS] Error forwarding to robot {robot_id}: {e}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "robot_id": robot_id,
                            "message": f"Error forwarding to robot: {str(e)}",
                            "timestamp": time.time()
                        }))
            except json.JSONDecodeError:
                logger.error(f"[WS] Invalid JSON from WebSocket Bridge: {message}")
            except Exception as e:
                logger.error(f"[WS] Error processing WebSocket message: {e}")
                logger.error(traceback.format_exc())
    except websockets.exceptions.ConnectionClosed:
        logger.info("[WS] WebSocket Bridge connection closed")
    except Exception as e:
        logger.error(f"[WS] Error in WebSocket Bridge handler: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Reset frontend bridge connection
        if frontend_bridge == websocket:
            frontend_bridge = None
        
        # Try to reconnect after delay
        await asyncio.sleep(5)
        asyncio.create_task(connect_to_ws_bridge())


# Thêm function is_heartbeat_message ando đầu file, sau các import
def is_heartbeat_message(data):
    """
    Kiểm tra xem tin nhắn có phải là heartbeat không
    
    Args:
        data: Dữ liệu tin nhắn (dict or object)
        
    Returns:
        bool: True nếu là tin nhắn heartbeat, False nếu không phải
    """
    # Nếu không phải dict, không phải heartbeat
    if not isinstance(data, dict):
        return False
    
    # Kiểm tra loại tin nhắn
    if data.get("type") in ["heartbeat", "ping", "pong"]:
        return True
    
    # Kiểm tra nếu chỉ có timestamp and ít hơn 3 trường
    if "timestamp" in data and len(data) <= 3:
        return True
    
    return False

# Sửa hàm connect_to_backend để xử lý lỗi tốt hơn and giới hạn thử lại
async def connect_to_backend(robot_id, max_retries=1):
    """
    Kết nối đến backend server thông qua WebSocket
    
    Args:
        robot_id: ID của robot
        max_retries: Số lần thử lại tối đa
    
    Returns:
        WebSocketClientProtocol: Kết nối WebSocket or None nếu không thành công
    """
    uri = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws/robot/{robot_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Origin": f"http://{BACKEND_HOST}:{BACKEND_PORT}",
        "X-Robot-ID": robot_id
    }
    
    logger.info(f"Connecting to backend at: {uri}")
    logger.info(f"Using headers: {headers}")
    
    retries = 0
    while retries < max_retries:
        try:
            connection = await websockets.connect(uri, extra_headers=headers)
            logger.info(f"Đã kết nối thành công tới backend cho robot {robot_id}")
            return connection
        except Exception as e:
            retries += 1
            logger.error(f"Lỗi kết nối tới backend cho robot {robot_id}: {e}")
            if retries < max_retries:
                logger.info(f"Thử kết nối lại ({retries}/{max_retries})...")
                await asyncio.sleep(2)
            
    logger.error(f"Không thể kết nối đến backend sau {max_retries} lần thử")
    return None

async def send_to_backend(robot_id, data):
    """Gửi dữ liệu từ robot đến backend"""
    if robot_id not in backend_connections:
        websocket = await connect_to_backend(robot_id)
        if not websocket:
            logger.error(f"Không thể gửi dữ liệu đến backend cho robot {robot_id}: Không có kết nối")
            return False
        backend_connections[robot_id] = websocket
    else:
        websocket = backend_connections[robot_id]
    
    try:
        # Đảm bảo có trường robot_id
        if isinstance(data, dict) and "robot_id" not in data:
            data["robot_id"] = robot_id
        
        # Gửi dữ liệu dưới dạng JSON
        await websocket.send(json.dumps(data))
        conditional_log("INFO", f"Đã gửi dữ liệu từ robot {robot_id} đến backend", is_heartbeat=is_heartbeat_message(data))
        return True
    except Exception as e:
        logger.error(f"Lỗi gửi dữ liệu đến backend cho robot {robot_id}: {e}")
        
        # Thử kết nối lại
        try:
            backend_connections[robot_id] = await connect_to_backend(robot_id)
        except:
            pass
        return False

# === ROBOT CONNECTION MANAGEMENT ===

def send_to_robot(robot_id, data):
    """
    Gửi dữ liệu từ TCP server đến robot
    
    Args:
        robot_id (str): ID của robot
        data (dict or str): Dữ liệu cần gửi
        
    Returns:
        bool: True nếu gửi thành công, False nếu thất bại
    """
    if robot_id not in robots:
        logger.error(f"Không thể gửi dữ liệu: Robot {robot_id} không kết nối")
        return False
    
    try:
        # Đảm bảo dữ liệu là JSON string + newline để robot dễ xử lý
        if isinstance(data, dict):
            data_str = json.dumps(data) + '\n'
        else:
            data_str = str(data) + '\n'
        
        # Gửi dữ liệu
        robots[robot_id].sendall(data_str.encode('utf-8'))
        
        # Log với mức độ phù hợp
        if isinstance(data, dict) and data.get("frontend", False):
            logger.debug(f"Đã gửi dữ liệu từ frontend đến robot {robot_id}: {data}")
        else:
            logger.info(f"Đã gửi dữ liệu đến robot {robot_id}: {data}")
            
        # Cập nhật thời gian hoạt động cuối cùng
        if robot_id in robot_data:
            robot_data[robot_id]["last_activity"] = time.time()
            
        return True
        
    except Exception as e:
        logger.error(f"Lỗi gửi dữ liệu đến robot {robot_id}: {e}")
        
        # Nếu lỗi kết nối, đánh dấu robot đã ngắt kết nối
        if robot_id in robots:
            del robots[robot_id]
        if robot_id in robot_data:
            del robot_data[robot_id]
        if robot_id in backend_connections and backend_connections[robot_id]:
            asyncio.create_task(backend_connections[robot_id].close())
            backend_connections[robot_id] = None
            
        return False

async def handle_robot_connection(client_socket, addr):
    """Xử lý kết nối từ robot"""
    client_id = f"{addr[0]}:{addr[1]}"
    buffer = ""
    robot_id = None
    
    try:
        # Gửi thông điệp chào
        welcome_msg = json.dumps({
            "type": "welcome",
            "message": "Connected to TCP server",
            "timestamp": time.time()
        }) + '\n'
        client_socket.sendall(welcome_msg.encode('utf-8'))
        
        # Đọc and xử lý dữ liệu từ robot
        while True:
            data = client_socket.recv(4096)
            if not data:
                logger.info(f"Robot {robot_id or client_id} đã ngắt kết nối")
                break
            
            # Xử lý dữ liệu nhận được, tách các thông điệp hoàn chỉnh
            buffer += data.decode('utf-8')
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                
                # Bỏ qua dòng trống
                if not line.strip():
                    continue
                
                try:
                    message = json.loads(line)
                    # Xử lý thông điệp từ robot
                    await process_robot_message(message, client_socket, client_id)
                    
                    # Lấy robot_id từ thông điệp nếu chưa có
                    if not robot_id and "robot_id" in message:
                        robot_id = message["robot_id"]
                        robots[robot_id] = client_socket
                        logger.info(f"Đã đăng ký robot {robot_id} từ {client_id}")
                        
                except json.JSONDecodeError:
                    logger.error(f"Dữ liệu JSON không hợp lệ từ {robot_id or client_id}: {line}")
                except Exception as e:
                    logger.error(f"Lỗi xử lý thông điệp từ {robot_id or client_id}: {e}")
    
    except Exception as e:
        logger.error(f"Lỗi xử lý kết nối từ {robot_id or client_id}: {e}")
    
    finally:
        # Dọn dẹp khi kết nối đóng
        if robot_id and robot_id in robots:
            del robots[robot_id]
        
        try:
            client_socket.close()
        except:
            pass
        
        logger.info(f"Đã đóng kết nối từ {robot_id or client_id}")

    # Sau khi robot kết nối thành công
    if robot_id:
        # Thông báo cho backend về việc robot kết nối
        try:
            # Sử dụng hàm send_to_backend để thông báo việc kết nối
            asyncio.create_task(send_to_backend(robot_id, {
                "type": "connection_status",
                "robot_id": robot_id,
                "status": "connected",
                "timestamp": time.time()
            }))
        except Exception as e:
            logger.error(f"Không thể thông báo cho backend: {e}")

async def process_robot_message(message, client_socket, client_id):
    """Xử lý thông điệp từ robot"""
    message_type = message.get("type", "unknown")
    robot_id = message.get("robot_id")
    
    # Xử lý thông điệp định danh
    if message_type == "identification":
        if not robot_id:
            logger.error(f"Thông điệp định danh thiếu robot_id: {message}")
            return
        
        # Lưu thông tin robot
        robots[robot_id] = client_socket
        logger.info(f"Robot {robot_id} đã kết nối (địa chỉ {client_id})")
        
        # Gửi xác nhận
        response = {
            "type": "identification_ack",
            "status": "success",
            "robot_id": robot_id,
            "message": f"Robot {robot_id} đã được đăng ký",
            "timestamp": time.time()
        }
        client_socket.sendall((json.dumps(response) + '\n').encode('utf-8'))
    
    # Gửi dữ liệu từ robot đến backend
    elif robot_id:
        # Chuyển tiếp dữ liệu đến backend
        await send_to_backend(robot_id, message)
        
        # Gửi xác nhận về robot
        response = {
            "type": "data_ack",
            "status": "received",
            "message_type": message_type,
            "timestamp": time.time()
        }
        client_socket.sendall((json.dumps(response) + '\n').encode('utf-8'))
    else:
        logger.warning(f"Thông điệp không có robot_id: {message}")

# === FRONTEND MESSAGE HANDLING ===

def handle_frontend_message(message):
    """Xử lý thông điệp từ frontend (qua WebSocket bridge)"""
    message_type = message.get("type", "unknown")
    robot_id = message.get("robot_id")
    
    if not robot_id:
        logger.error(f"Thông điệp từ frontend thiếu robot_id: {message}")
        return {
            "type": "error",
            "status": "error",
            "message": "Thiếu robot_id trong thông điệp",
            "timestamp": time.time()
        }
    
    # THÔNG ĐIỆP LOẠI PID CONFIG
    if message_type == "pid_config":
        motor_id = message.get("motor_id", 1)
        parameters = message.get("parameters", {})
        
        logger.info(f"Nhận cấu hình PID từ frontend cho robot {robot_id}, motor {motor_id}: {parameters}")
        
        # Chuyển tiếp đến robot
        if send_to_robot(robot_id, message):
            return {
                "type": "pid_response",
                "status": "success",
                "robot_id": robot_id,
                "motor_id": motor_id,
                "message": f"Cấu hình PID đã được gửi đến robot {robot_id}",
                "timestamp": time.time()
            }
        else:
            return {
                "type": "pid_response",
                "status": "error",
                "robot_id": robot_id,
                "motor_id": motor_id,
                "message": f"Không thể gửi cấu hình PID: Robot {robot_id} không kết nối",
                "timestamp": time.time()
            }
    
    # THÔNG ĐIỆP LOẠI MOTOR CONTROL
    elif message_type == "motor_control":
        speeds = message.get("speeds", [0, 0, 0])
        
        logger.info(f"Nhận lệnh điều khiển động cơ từ frontend cho robot {robot_id}: speeds={speeds}")
        
        # Chuyển tiếp đến robot
        if send_to_robot(robot_id, message):
            return {
                "type": "motor_response",
                "status": "success",
                "robot_id": robot_id,
                "speeds": speeds,
                "message": f"Lệnh điều khiển đã được gửi đến robot {robot_id}",
                "timestamp": time.time()
            }
        else:
            return {
                "type": "motor_response",
                "status": "error",
                "robot_id": robot_id,
                "message": f"Không thể gửi lệnh điều khiển: Robot {robot_id} không kết nối",
                "timestamp": time.time()
            }
    
    # THÔNG ĐIỆP LOẠI FIRMWARE UPDATE
    elif message_type == "firmware_update":
        version = message.get("version", "unknown")
        
        logger.info(f"Nhận lệnh cập nhật firmware từ frontend cho robot {robot_id}: version={version}")
        
        # Chuyển tiếp đến robot
        if send_to_robot(robot_id, message):
            return {
                "type": "firmware_response",
                "status": "success",
                "robot_id": robot_id,
                "version": version,
                "message": f"Lệnh cập nhật firmware đã được gửi đến robot {robot_id}",
                "timestamp": time.time()
            }
        else:
            return {
                "type": "firmware_response",
                "status": "error",
                "robot_id": robot_id,
                "message": f"Không thể gửi lệnh cập nhật firmware: Robot {robot_id} không kết nối",
                "timestamp": time.time()
            }
    
    # THÔNG ĐIỆP LOẠI EMERGENCY STOP
    elif message_type == "emergency_stop":
        logger.info(f"Nhận lệnh dừng khẩn cấp từ frontend cho robot {robot_id}")
        
        # Chuyển tiếp đến robot
        if send_to_robot(robot_id, message):
            return {
                "type": "emergency_response",
                "status": "success",
                "robot_id": robot_id,
                "message": f"Lệnh dừng khẩn cấp đã được gửi đến robot {robot_id}",
                "timestamp": time.time()
            }
        else:
            return {
                "type": "emergency_response",
                "status": "error",
                "robot_id": robot_id,
                "message": f"Không thể gửi lệnh dừng khẩn cấp: Robot {robot_id} không kết nối",
                "timestamp": time.time()
            }
    
    # THÔNG ĐIỆP LOẠI KHÁC
    else:
        logger.warning(f"Nhận loại thông điệp không xác định từ frontend: {message_type}")
        
        # Chuyển tiếp đến robot nếu có chỉ định robot_id
        if robot_id in robots:
            send_to_robot(robot_id, message)
            return {
                "type": "generic_response",
                "status": "success",
                "robot_id": robot_id,
                "message": f"Thông điệp đã được chuyển tiếp đến robot {robot_id}",
                "timestamp": time.time()
            }
        else:
            return {
                "type": "generic_response",
                "status": "error",
                "robot_id": robot_id,
                "message": f"Không thể chuyển tiếp thông điệp: Robot {robot_id} không kết nối",
                "timestamp": time.time()
            }

# === SERVER STARTUP ===

async def handle_websocket_connection(websocket, path):
    """Xử lý kết nối WebSocket"""
    addr = websocket.remote_address
    client_id = f"{addr[0]}:{addr[1]}" if addr else "unknown"
    logger.info(f"[WS] Kết nối WebSocket mới từ {client_id}")
    logger.info(f"[WS] WebSocket path: {path}")
    
    # Xử lý kết nối từ WebSocket Bridge
    if path == "/bridge":
        logger.info(f"[WS] Phát hiện kết nối WebSocket Bridge từ {client_id}")
        await handle_bridge_message(websocket)
        return
    
    # Xử lý kết nối từ robot
    robot_id = None
    try:
        # Chờ tin nhắn đăng ký đầu tiên
        logger.info(f"[WS] Đợi tin nhắn đăng ký từ {client_id}...")
        registration_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
        logger.info(f"[WS] Nhận tin nhắn đăng ký từ {client_id}: {registration_message[:200]}" + 
                  ("..." if len(registration_message) > 200 else ""))
        
        data = json.loads(registration_message)
        
        # Lấy robot_id từ tin nhắn
        robot_id = data.get("robot_id")
        
        if not robot_id:
            logger.error(f"[WS] Không có robot_id trong tin nhắn đăng ký từ {client_id}")
            await websocket.close(1008, "Missing robot_id")
            return
            
        # Đăng ký robot
        robots[robot_id] = websocket
        robot_data[robot_id] = data
        
        logger.info(f"[WS] Đã đăng ký robot {robot_id} từ {client_id}")
        
        
        # Gửi xác nhận đăng ký
        try:
            confirm_msg = {
                "type": "registration_confirmation",
                "robot_id": robot_id,
                "status": "success",
                "timestamp": time.time()
            }
            await websocket.send(json.dumps(confirm_msg))
            logger.info(f"[WS] Đã gửi xác nhận đăng ký đến {robot_id}")
        except Exception as e:
            logger.error(f"[WS] Lỗi gửi xác nhận đăng ký: {e}")
        
        # Xử lý tin nhắn từ robot
        await handle_robot_messages(robot_id, websocket)
        
    except asyncio.TimeoutError:
        logger.error(f"[WS] Timeout chờ tin nhắn đăng ký từ {client_id}")
        await websocket.close(1013, "Registration timeout")
    except json.JSONDecodeError:
        logger.error(f"[WS] Tin nhắn đăng ký không hợp lệ từ {client_id}")
        await websocket.close(1008, "Invalid registration")
    except Exception as e:
        logger.error(f"[WS] Lỗi xử lý kết nối WebSocket từ {client_id}: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Dọn dẹp kết nối
        if robot_id in robots:
            logger.info(f"[WS] Xóa robot {robot_id} khỏi danh sách robots")
            del robots[robot_id]
        if robot_id in robot_data:
            logger.info(f"[WS] Xóa robot {robot_id} khỏi danh sách robot_data")
            del robot_data[robot_id]

# Thêm heartbeat để duy trì kết nối
async def start_heartbeat():
    """Gửi heartbeat đến tất cả các kết nối để duy trì kết nối"""
    while True:
        try:
            # Gửi heartbeat đến tất cả bridge connections
            for robot_id, conn in bridge_connections.items():
                try:
                    if conn and conn.open:
                        await conn.send(json.dumps({
                            "type": "heartbeat",
                            "timestamp": time.time()
                        }))
                except Exception as e:
                    logger.error(f"Lỗi gửi heartbeat đến bridge {robot_id}: {e}")
                    
            # Đợi 30 giây
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Lỗi trong heartbeat: {e}")
            await asyncio.sleep(30)  # Thử lại sau 30 giây

async def start_server(host='0.0.0.0', port=9000, ws_port=9002):
    """Khởi động TCP server and WebSocket server"""
    # Tạo TCP Server cho robot
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    logger.info(f"TCP Server đã khởi động trên {host}:{port}")
    
    # Tạo WebSocket Server cho frontend
    ws_server = await websockets.serve(handle_websocket_connection, host, ws_port)
    logger.info(f"WebSocket Server cho frontend đã khởi động trên {host}:{ws_port}")
    
    # Xử lý kết nối TCP từ robot
    def handle_connections():
        while True:
            try:
                client_socket, addr = server.accept()
                logger.info(f"Kết nối mới từ {addr[0]}:{addr[1]}")
                
                # Tạo thread mới cho mỗi kết nối
                client_thread = threading.Thread(
                    target=lambda: asyncio.run(handle_robot_connection(client_socket, addr)),
                    daemon=True
                )
                client_thread.start()
            except Exception as e:
                logger.error(f"Lỗi xử lý kết nối mới: {e}")
    
    # Khởi động thread xử lý kết nối TCP 
    connection_thread = threading.Thread(target=handle_connections, daemon=True)
    connection_thread.start()
    
    # Khởi động heartbeat
    asyncio.create_task(start_heartbeat())
    
    # Connect to WebSocket Bridge
    asyncio.create_task(connect_to_ws_bridge())
    
    # Giữ async event loop chạy
    try:
        await asyncio.Future()  # Chạy mãi mãi
    finally:
        server.close()
        ws_server.close()

        # Khởi động task monitoring
        asyncio.create_task(monitor_connections())
        
        # Giữ server hoạt động
        while True:
            await asyncio.sleep(3600)  # Chờ 1 giờ
    
    # Hàm để giám sát các kết nối
    async def monitor_connections():
        """Giám sát các kết nối and làm sạch các kết nối đã mất"""
        while True:
            try:
                # Kiểm tra kết nối robot
                with robots_lock:
                    for robot_id in list(robots.keys()):
                        # Kiểm tra xem robot còn kết nối không
                        if robot_id in robot_data:
                            last_activity = robot_data[robot_id].get("last_activity", 0)
                            if time.time() - last_activity > 300:  # 5 phút không hoạt động
                                logger.warning(f"Robot {robot_id} không hoạt động trong 5 phút, đánh dấu là ngắt kết nối")
                                try:
                                    del robots[robot_id]
                                except KeyError:
                                    pass
    
                # Kiểm tra kết nối backend
                for robot_id in list(backend_connections.keys()):
                    ws = backend_connections.get(robot_id)
                    if ws and not ws.open:
                        logger.warning(f"Kết nối backend cho robot {robot_id} đã đóng, xóa khỏi danh sách")
                        backend_connections[robot_id] = None
    
                # Đợi 60 giây trước khi kiểm tra lại
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Lỗi trong monitor_connections: {e}")
                await asyncio.sleep(60)  # Vẫn đợi trước khi thử lại

# Entry point
if __name__ == "__main__":
    logger.info("Khởi động TCP Server...")
    asyncio.run(start_server())

# Trong hàm handle_data or process_message, thêm xử lý cho các loại yêu cầu mới

def handle_data(client_socket, client_id, robot_id, data):
    """Xử lý dữ liệu từ client"""
    data_type = data.get("type", "unknown")
    
    # Kiểm tra nếu là heartbeat or các loại thông điệp thường xuyên
    is_frequent_message = data_type in ["get_robot_connections", "heartbeat", "ping", "status"]
    
    if data_type == "get_robot_connections":
        # Chỉ log nếu LOG_HEARTBEATS được bật
        if LOG_HEARTBEATS:
            logger.info(f"Xử lý yêu cầu get_robot_connections từ {client_id}")
        
        # Tạo danh sách các robot đang kết nối
        robot_connections = {}
        with robots_lock:
            for rid in robots:
                robot_connections[rid] = robots[rid]["connected"]
        
        # Gửi thông tin kết nối robot
        response = {
            "type": "robot_status_update",
            "robot_connections": robot_connections,
            "robot_id": data.get("robot_id", "robot1"),
            "timestamp": time.time()
        }
        
        # Chỉ log thông tin này nếu LOG_DETAILED_MESSAGES được bật
        if LOG_DETAILED_MESSAGES:
            logger.info(f"Đang gửi thông tin kết nối robot: {robot_connections}")
        
        return response
    
    # Xử lý yêu cầu giả lập kết nối robot
    elif data_type == "connect_robot_simulator":
        target_robot_id = data.get("robot_id", "robot1")
        
        logger.info(f"Nhận yêu cầu giả lập kết nối robot: {target_robot_id}")
        
        # Tạo thread giả lập kết nối robot
        threading.Thread(
            target=simulate_robot_connection,
            args=(target_robot_id,),
            daemon=True
        ).start()
        
        return {
            "type": "simulator_response",
            "status": "success",
            "message": f"Đang khởi tạo kết nối giả lập cho robot {target_robot_id}",
            "robot_id": target_robot_id,
            "timestamp": time.time()
        }
    
    # Xử lý lệnh get_robot_list
    if data_type == "get_robot_list":
        # Tạo danh sách robot kèm thông tin
        robot_list = []
        with robots_lock:
            for rid, info in robots.items():
                robot_list.append({
                    "id": rid,
                    "connected": info["connected"],
                    "ip": info.get("address", "unknown"),
                    "last_seen": time.strftime("%H:%M:%S", time.localtime(info.get("last_seen", time.time())))
                })
        
        # Thông tin điện thoại mới kết nối
        # Kiểm tra nếu có kết nối từ điện thoại (IP không phải 127.0.0.1)
        with clients_lock:
            for cid, socket_info in clients.items():
                if "127.0.0.1" not in cid and socket_info.get("robot_id") is None:
                    parts = cid.split(":")
                    if len(parts) == 2:
                        ip = parts[0]
                        # Thêm điện thoại ando danh sách, gán tạm là robot1 nếu chưa xác định
                        phone_robot_id = "phone_" + ip.replace(".", "_")
                        robot_list.append({
                            "id": "robot1",  # Gán tạm là robot1
                            "connected": True,
                            "ip": ip,
                            "last_seen": time.strftime("%H:%M:%S", time.localtime(time.time())),
                            "device_type": "phone"
                        })
        
        # Gửi phản hồi
        response = {
            "type": "robot_list",
            "robots": robot_list,
            "timestamp": time.time()
        }
        
        logger.info(f"Đang gửi danh sách robot: {robot_list}")
        return response
    
    # Còn lại các xử lý khác...

# Thêm hàm để giả lập kết nối robot
def simulate_robot_connection(robot_id):
    """Giả lập kết nối từ robot đến TCP server"""
    try:
        logger.info(f"Đang giả lập kết nối cho robot {robot_id}")
        
        # Tạo socket kết nối đến TCP server
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('localhost', 9000))
        
        # Nhận welcome message
        welcome = client.recv(4096).decode('utf-8')
        logger.info(f"Giả lập nhận welcome: {welcome}")
        
        # Gửi thông điệp nhận dạng
        identify_msg = {
            "type": "identification",
            "robot_id": robot_id,
            "hardware": "ESP32 (Giả lập)",
            "firmware_version": "1.0.0",
            "timestamp": time.time()
        }
        client.send((json.dumps(identify_msg) + '\n').encode('utf-8'))
        
        # Nhận phản hồi
        response = client.recv(4096).decode('utf-8')
        logger.info(f"Giả lập nhận phản hồi: {response}")
        
        # Gửi dữ liệu cảm biến giả lập định kỳ
        while True:
            try:
                # Tạo dữ liệu giả lập
                sensor_data = {
                    "type": "sensor_data",
                    "robot_id": robot_id,
                    "battery": random.randint(70, 100),
                    "temperature": random.uniform(25, 35),
                    "encoder": [random.randint(0, 100) for _ in range(3)],
                    "timestamp": time.time()
                }
                
                # Gửi dữ liệu
                client.send((json.dumps(sensor_data) + '\n').encode('utf-8'))
                logger.info(f"Giả lập gửi dữ liệu cảm biến từ {robot_id}")
                
                # Ngủ một khoảng thời gian
                time.sleep(5)
            except socket.error as e:
                logger.error(f"Lỗi socket khi gửi dữ liệu giả lập: {e}")
                break
            except Exception as e:
                logger.error(f"Lỗi không xác định khi gửi dữ liệu giả lập: {e}")
                break
                
            except Exception as e:
                logger.error(f"Lỗi trong giả lập robot {robot_id}: {e}")
                break
        
    except Exception as e:
        logger.error(f"Lỗi khởi tạo giả lập cho robot {robot_id}: {e}")
    finally:
        # Đánh dấu robot ngắt kết nối khi kết thúc
        with robots_lock:
            if robot_id in robots:
                robots[robot_id]["connected"] = False
                robots[robot_id]["socket"] = None
        logger.info(f"Kết thúc giả lập kết nối cho robot {robot_id}")

# Sửa lỗi 'int' object has no attribute 'get'
def handle_client_message(client_socket, client_id, data_str):
    """Xử lý thông điệp từ client"""
    try:
        # Parse dữ liệu
        if isinstance(data_str, str):
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                return {'type': 'error', 'status': 'error', 'message': 'Dữ liệu không phải JSON hợp lệ'}
        else:
            data = data_str
        
        # Kiểm tra loại thông điệp
        if not isinstance(data, dict) or "type" not in data:
            return {'type': 'error', 'status': 'error', 'message': 'Thiếu trường type trong thông điệp'}
        
        message_type = data.get("type", "")
        
        # QUAN TRỌNG: Thêm robot_id cho get_robot_connections nếu thiếu
        if message_type == "get_robot_connections" and "robot_id" not in data:
            data["robot_id"] = "robot1"  # Thêm robot_id mặc định
            logger.debug(f"Đã tự động thêm robot_id=robot1 ando lệnh get_robot_connections")
        
        # Skip kiểm tra robot_id cho một số loại tin nhắn đặc biệt
        special_message_types = ["get_robot_connections", "get_server_status", "ping", "heartbeat"]
        
        # Kiểm tra có robot_id hay không (trừ các loại tin nhắn đặc biệt)
        if "robot_id" not in data and message_type not in special_message_types:
            return {'type': 'error', 'status': 'error', 'message': 'Thiếu robot_id trong thông điệp'}
        
        # Xử lý các loại thông điệp
        if message_type == "get_robot_connections":
            # Tạo danh sách các robot đang kết nối
            robot_connections = {}
            with robots_lock:
                for rid in robots:
                    robot_connections[rid] = robots[rid]["connected"]
            
            # Gửi thông tin kết nối robot
            return {
                "type": "robot_status_update",
                "robot_connections": robot_connections,
                "robot_id": data.get("robot_id", "robot1"),  # Sử dụng robot_id từ request or mặc định
                "timestamp": time.time()
            }
            
        # Xử lý các loại thông điệp khác
        # Tiếp tục xử lý...
    except Exception as e:
        logger.error(f"Lỗi xử lý thông điệp từ {client_id}: {e}")
        return {'type': 'error', 'message': str(e)}

# Sửa hàm handle_phone_connection có chứa lỗi cú pháp
async def handle_phone_connection(client_socket, addr):
    """Xử lý kết nối từ điện thoại"""
    client_id = f"{addr[0]}:{addr[1]}"
    
    with clients_lock:
        clients[client_id] = {
            "socket": client_socket,
            "robot_id": None,  # Chưa xác định robot_id
            "device_type": "phone"
        }
    
    try:
        # Gửi welcome message
        welcome_msg = json.dumps({
            "type": "welcome",
            "message": "Connected to TCP server",
            "timestamp": time.time()
        }) + '\n'
        client_socket.sendall(welcome_msg.encode('utf-8'))
        
        logger.info(f"Điện thoại kết nối từ {client_id}")
        
        # Cập nhật robot1 có kết nối mới
        with robots_lock:
            if "robot1" in robots:
                # Cập nhật trạng thái robot1 là đã kết nối
                robots["robot1"]["connected"] = True
                robots["robot1"]["last_seen"] = time.time()
                robots["robot1"]["socket"] = client_socket
                robots["robot1"]["address"] = addr[0]
            else:
                # Tạo mới robot1 nếu chưa có
                robots["robot1"] = {
                    "connected": True,
                    "socket": client_socket,
                    "last_seen": time.time(),
                    "address": addr[0]
                }
        
        buffer = ""
        # Vòng lặp nhận dữ liệu
        while True:
            try:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                # Xử lý dữ liệu từ điện thoại
                try:
                    # Có thể dữ liệu không phải JSON
                    str_data = data.decode('utf-8').strip()
                    logger.info(f"Nhận dữ liệu từ điện thoại {client_id}: {str_data}")
                    
                    # Gửi ACK
                    ack_msg = json.dumps({
                        "type": "data_ack",
                        "status": "received",
                        "timestamp": time.time()
                    }) + '\n'
                    client_socket.sendall(ack_msg.encode('utf-8'))
                    
                except Exception as e:
                    logger.error(f"Lỗi xử lý dữ liệu từ điện thoại {client_id}: {e}")
            except Exception as e:
                logger.error(f"Lỗi nhận dữ liệu từ điện thoại {client_id}: {e}")
                break  # Thoát vòng lặp nếu có lỗi
    
    except Exception as e:
        logger.error(f"Lỗi xử lý kết nối từ điện thoại {client_id}: {e}")
    finally:
        logger.info(f"Đóng kết nối từ điện thoại {client_id}")
        
        # Cập nhật trạng thái robot1
        with robots_lock:
            if "robot1" in robots:
                robots["robot1"]["connected"] = False
                robots["robot1"]["socket"] = None
        
        # Đóng socket and xóa khỏi danh sách
        try:
            client_socket.close()
        except:
            pass
        
        with clients_lock:
            if client_id in clients:
                del clients[client_id]

# Hàm kiểm tra nếu là heartbeat message
def is_heartbeat_message(data):
    """
    Kiểm tra xem tin nhắn có phải là heartbeat không
    
    Args:
        data: Dữ liệu tin nhắn (dict or object)
        
    Returns:
        bool: True nếu là tin nhắn heartbeat, False nếu không phải
    """
    # Nếu không phải dict, không phải heartbeat
    if not isinstance(data, dict):
        return False
    
    # Kiểm tra loại tin nhắn
    if data.get("type") in ["heartbeat", "ping", "pong"]:
        return True
    
    # Kiểm tra nếu chỉ có timestamp and ít hơn 3 trường
    if "timestamp" in data and len(data) <= 3:
        return True
    
    return False

# Thêm hàm kiểm tra loại tin nhắn đặc biệt
def is_special_message(message_type):
    """Kiểm tra xem tin nhắn có phải loại đặc biệt không yêu cầu robot_id"""
    special_types = ["get_robot_connections", "get_server_status", "ping", "heartbeat", "connect_robot_simulator"]
    return message_type in special_types

# Sửa hàm xử lý tin nhắn từ WebSocket Bridge
def handle_ws_bridge_message(message):
    """Xử lý tin nhắn từ WebSocket Bridge"""
    try:
        # Kiểm tra dữ liệu
        if not isinstance(message, dict) or "type" not in message:
            logger.error("Tin nhắn từ WebSocket Bridge không hợp lệ")
            return {
                "type": "error",
                "status": "error",
                "message": "Tin nhắn không hợp lệ (thiếu type)",
                "timestamp": time.time()
            }
        
        message_type = message.get("type")
        
        # Xử lý các loại tin nhắn đặc biệt
        if is_special_message(message_type):
            # Đảm bảo có robot_id cho tin nhắn đặc biệt
            if "robot_id" not in message:
                message["robot_id"] = "robot1"
                logger.debug(f"Đã thêm robot_id cho tin nhắn {message_type}")
        elif "robot_id" not in message:
            logger.error(f"Thông điệp từ frontend thiếu robot_id: {message}")
            return {
                "type": "error",
                "status": "error",
                "message": "Thiếu robot_id trong thông điệp",
                "timestamp": time.time()
            }
        
        try:
            # Tiếp tục xử lý tin nhắn
            # Thêm code xử lý tin nhắn ở đây
            return {
                "type": "response",
                "status": "success",
                "message": f"Đã xử lý tin nhắn loại {message_type}",
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Lỗi khi xử lý tin nhắn {message_type}: {e}")
            return {
                "type": "error",
                "status": "error", 
                "message": f"Lỗi xử lý: {str(e)}",
                "timestamp": time.time()
            }
    except Exception as e:
        logger.error(f"Lỗi xử lý tin nhắn từ WebSocket Bridge: {e}")
        return {
            "type": "error",
            "status": "error",
            "message": f"Lỗi xử lý tin nhắn: {str(e)}",
            "timestamp": time.time()
        }

# Thêm or cập nhật hàm xử lý connect_robot_simulator
def handle_connect_robot_simulator(data):
    """Xử lý lệnh mô phỏng kết nối robot"""
    robot_id = data.get("robot_id", "robot1")
    
    with robots_lock:
        # Kiểm tra xem robot đã tồn tại chưa
        if robot_id not in robots:
            robots[robot_id] = {
                "socket": None,
                "connected": True,  # Thiết lập trạng thái kết nối là True
                "last_seen": time.time(),
                "simulated": True  # Đánh dấu đây là robot mô phỏng
            }
            logger.info(f"Đã tạo robot mô phỏng: {robot_id}")
        else:
            # Cập nhật trạng thái kết nối
            robots[robot_id]["connected"] = True
            robots[robot_id]["last_seen"] = time.time()
            robots[robot_id]["simulated"] = True
            logger.info(f"Đã cập nhật robot mô phỏng: {robot_id}")
    
    # Khởi động thread giả lập robot
    threading.Thread(
        target=simulate_robot_connection,
        args=(robot_id,),
        daemon=True
    ).start()
    
    return {
        "type": "robot_connection_update",
        "status": "success",
        "robot_id": robot_id,
        "connected": True,
        "timestamp": time.time()
    }

# Thêm hàm is_heartbeat_message ở đầu file, sau các import
def is_heartbeat_message(data):
    """
    Kiểm tra xem tin nhắn có phải là heartbeat không để tránh gửi quá nhiều tin nhắn đến backend
    
    Args:
        data (dict): Dữ liệu tin nhắn cần kiểm tra
        
    Returns:
        bool: True nếu là tin nhắn heartbeat, False nếu không phải
    """
    if not isinstance(data, dict):
        return False
        
    # Kiểm tra các loại tin nhắn heartbeat thông dụng
    if data.get("type") in ["ping", "pong", "heartbeat"]:
        return True
    
    # Kiểm tra nếu tin nhắn chỉ chứa thông tin timestamp mà không có dữ liệu khác
    if "timestamp" in data and len(data) < 3:
        return True
        
    return False

# Cập nhật hàm handle_robot_messages để sử dụng hàm is_heartbeat_message
async def handle_robot_messages(robot_id, websocket):
    """Xử lý tin nhắn từ robot"""
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}" if hasattr(websocket, 'remote_address') else "unknown"
    logger.info(f"[ROBOT] Bắt đầu xử lý tin nhắn từ robot {robot_id} (client: {client_id})")
    
    try:
        # Đọc tin nhắn từ robot
        async for message in websocket:
            try:
                # Log tin nhắn raw nhận được
                logger.debug(f"[ROBOT] Raw từ {robot_id}: {message[:100]}...")
                
                # Xử lý tin nhắn
                data = parse_robot_message(message)
                
                # Phân loại tin nhắn
                msg_type = data.get("type", "unknown")
                is_heartbeat = is_heartbeat_message(data)
                
                # Log tin nhắn (trừ khi là heartbeat thì chỉ log debug)
                if is_heartbeat:
                    logger.debug(f"[ROBOT] Heartbeat từ {robot_id}")
                else:
                    logger.info(f"[ROBOT] Nhận từ {robot_id}: type={msg_type}, data={data}")
                
                # Chuyển tiếp đến bridge websocket nếu có
                if frontend_bridge:
                    try:
                        await frontend_bridge.send(json.dumps(data))
                        if not is_heartbeat:
                            logger.info(f"[ROBOT] Đã chuyển tiếp từ {robot_id} đến WebSocket Bridge: type={msg_type}")
                    except Exception as e:
                        logger.error(f"[ROBOT] Lỗi gửi dữ liệu từ {robot_id} đến WebSocket Bridge: {e}")
                else:
                    logger.debug(f"[ROBOT] Không có WebSocket Bridge để gửi dữ liệu từ {robot_id}")
                
                # Chuyển tiếp đến backend
                if robot_id in backend_connections and backend_connections[robot_id]:
                    # Bỏ qua các tin nhắn heartbeat để giảm tải backend
                    if not is_heartbeat:  
                        try:
                            await backend_connections[robot_id].send(json.dumps(data))
                            logger.info(f"[ROBOT] Đã gửi dữ liệu từ robot {robot_id} đến backend")
                        except Exception as e:
                            logger.error(f"[ROBOT] Lỗi gửi dữ liệu đến backend cho robot {robot_id}: {e}")
                            # Nếu lỗi kết nối, thử kết nối lại
                            backend_connections[robot_id] = await connect_to_backend(robot_id)
                
                
                # Xử lý các lệnh đặc biệt nếu cần
                if "command" in data:
                    # Xử lý lệnh từ robot
                    logger.info(f"[ROBOT] Xử lý lệnh từ robot {robot_id}: {data.get('command')}")
                    handle_robot_command(robot_id, data)
                    
            except json.JSONDecodeError as e:
                logger.error(f"[ROBOT] Lỗi parse JSON từ robot {robot_id}: {e}")
                logger.error(f"[ROBOT] Dữ liệu gốc: {message[:100]}...")
            except Exception as e:
                logger.error(f"[ROBOT] Lỗi xử lý tin nhắn từ robot {robot_id}: {e}")
                logger.error(traceback.format_exc())
                
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"[ROBOT] Đóng kết nối với robot {robot_id}: {e}")
    except Exception as e:
        logger.error(f"[ROBOT] Lỗi không xác định với robot {robot_id}: {e}")
        logger.error(traceback.format_exc())
    finally:
        logger.info(f"[ROBOT] Kết thúc xử lý tin nhắn từ robot {robot_id}")

def parse_robot_message(message):
    """
    Parse thông điệp từ robot
    
    Args:
        message: Thông điệp từ robot (string or bytes)
        
    Returns:
        dict: Thông điệp đã parse
    """
    if isinstance(message, bytes):
        message = message.decode('utf-8')
    
    message = message.strip()
    
    try:
        # Thử parse JSON
        data = json.loads(message)
        return data
    except json.JSONDecodeError:
        # Nếu không phải JSON, trả về dạng text
        return {
            "type": "text_message",
            "message": message,
            "timestamp": time.time()
        }

def handle_robot_command(robot_id, data):
    """
    Xử lý lệnh từ robot
    
    Args:
        robot_id (str): ID của robot
        data (dict): Dữ liệu lệnh
    """
    command = data.get("command")
    
    logger.info(f"Xử lý lệnh '{command}' từ robot {robot_id}")
    
    if command == "restart":
        # Xử lý lệnh restart
        logger.info(f"Nhận lệnh restart từ robot {robot_id}")
        # Thực hiện restart logic nếu cần
        
    elif command == "update_config":
        # Xử lý lệnh cập nhật cấu hình
        logger.info(f"Nhận lệnh update_config từ robot {robot_id}")
        # Thực hiện cập nhật cấu hình nếu cần
        
    elif command == "diagnostic":
        # Xử lý lệnh chẩn đoán
        logger.info(f"Nhận lệnh diagnostic từ robot {robot_id}")
        # Thực hiện chẩn đoán nếu cần
    
    # Trả về ack
    response = {
        "type": "command_ack",
        "command": command,
        "status": "processed",
        "timestamp": time.time()
    }
    
    # Gửi phản hồi đến robot
    send_to_robot(robot_id, response)

async def handle_bridge_message(websocket):
    """Xử lý kết nối WebSocket Bridge"""
    global frontend_bridge
    addr = websocket.remote_address
    client_id = f"{addr[0]}:{addr[1]}" if addr else "unknown"
    
    # Thiết lập bridge connection
    frontend_bridge = websocket
    bridge_id = f"bridge-{client_id}"
    bridge_connections[bridge_id] = websocket
    
    logger.info(f"[BRIDGE] WebSocket Bridge đã kết nối từ {client_id}")
    
    # Gửi welcome message
    try:
        welcome_msg = {
            "type": "welcome",
            "message": "Connected to TCP server via WebSocket Bridge",
            "timestamp": time.time()
        }
        await websocket.send(json.dumps(welcome_msg))
        logger.info(f"[BRIDGE] Đã gửi welcome đến WebSocket Bridge: {welcome_msg}")
    except Exception as e:
        logger.error(f"[BRIDGE] Lỗi gửi welcome message đến bridge: {e}")
    
    # Log trạng thái kết nối hiện tại
    logger.info(f"[BRIDGE] Số robots đang kết nối: {len(robots)}")
    for rid, _ in robots.items():
        logger.info(f"[BRIDGE] - Robot đang kết nối: {rid}")
    
    try:
        # Xử lý tin nhắn từ bridge
        async for message in websocket:
            try:
                # Log tin nhắn raw nhận được
                logger.debug(f"[BRIDGE] Raw từ {client_id}: {message[:100]}...")
                
                # Parse JSON
                data = json.loads(message)
                
                # Phân loại tin nhắn
                msg_type = data.get("type", "unknown")
                robot_id = data.get("robot_id", "unknown")
                is_heartbeat = is_heartbeat_message(data)
                
                # Log chi tiết (trừ heartbeat)
                if is_heartbeat:
                    logger.debug(f"[BRIDGE] Heartbeat từ bridge: {data}")
                else:
                    logger.info(f"[BRIDGE] Nhận từ bridge: type={msg_type}, robot_id={robot_id}")
                    logger.debug(f"[BRIDGE] Chi tiết: {data}")
                
                # Xử lý thông điệp
                response = handle_frontend_message(data)
                
                # Gửi phản hồi về WebSocket Bridge
                await websocket.send(json.dumps(response))
                logger.info(f"[BRIDGE] Đã gửi phản hồi đến bridge: type={response.get('type', 'unknown')}, status={response.get('status', 'unknown')}")
                logger.debug(f"[BRIDGE] Chi tiết phản hồi: {response}")
                
            except json.JSONDecodeError:
                logger.error(f"[BRIDGE] Dữ liệu JSON không hợp lệ từ bridge: {message[:100]}...")
                await websocket.send(json.dumps({
                    "type": "error",
                    "status": "invalid_json",
                    "message": "Định dạng JSON không hợp lệ",
                    "timestamp": time.time()
                }))
            except Exception as e:
                logger.error(f"[BRIDGE] Lỗi xử lý thông điệp từ bridge: {e}")
                logger.error(traceback.format_exc())
                await websocket.send(json.dumps({
                    "type": "error",
                    "status": "error",
                    "message": f"Lỗi xử lý thông điệp: {str(e)}",
                    "timestamp": time.time()
                }))
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"[BRIDGE] WebSocket Bridge đã ngắt kết nối: {e}")
    except Exception as e:
        logger.error(f"[BRIDGE] Lỗi với WebSocket Bridge: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Dọn dẹp kết nối
        if frontend_bridge == websocket:
            logger.info(f"[BRIDGE] Xóa frontend_bridge")
            frontend_bridge = None
        if bridge_id in bridge_connections:
            logger.info(f"[BRIDGE] Xóa {bridge_id} khỏi bridge_connections")
            del bridge_connections[bridge_id]
        logger.info(f"[BRIDGE] Đã đóng kết nối WebSocket Bridge từ {client_id}")

def handle_message(data):
    """
    Xử lý các loại thông điệp chung từ client
    
    Args:
        data (dict): Dữ liệu tin nhắn
        
    Returns:
        dict: Phản hồi cho client
    """
    message_type = data.get("type", "unknown")
    robot_id = data.get("robot_id", "unknown")
    
    logger.info(f"Xử lý thông điệp chung: type={message_type}, robot_id={robot_id}")
    
    # Kiểm tra các loại tin nhắn phổ biến
    if message_type == "heartbeat":
        return {
            "type": "heartbeat_ack",
            "timestamp": time.time()
        }
    
    elif message_type == "get_robot_status" and robot_id != "unknown":
        # Kiểm tra trạng thái robot
        is_connected = False
        if robot_id in robots:
            is_connected = True
        elif robot_id in tcp_robots:
            is_connected = True
            
        return {
            "type": "robot_status",
            "robot_id": robot_id,
            "connected": is_connected,
            "timestamp": time.time()
        }
        
    elif message_type == "get_server_info":
        # Trả về thông tin server
        return {
            "type": "server_info",
            "version": "1.0.0",
            "uptime": int(time.time() - start_time),
            "robots_count": len(robots) + len(tcp_robots),
            "timestamp": time.time()
        }
    
    elif message_type == "ping":
        return {
            "type": "pong",
            "timestamp": time.time()
        }
    
    # Trường hợp tin nhắn có chứa robot_id nhưng không phải loại đặc biệt
    elif robot_id != "unknown":
        # Chuyển tiếp tin nhắn đến robot nếu có thể
        forwarded = False
        
        if robot_id in robots:
            try:
                # Robot kết nối qua WebSocket
                asyncio.create_task(robots[robot_id].send(json.dumps(data)))
                logger.info(f"Đã chuyển tiếp tin nhắn tới robot {robot_id} qua WebSocket")
                forwarded = True
            except Exception as e:
                logger.error(f"Không thể chuyển tiếp tin nhắn đến robot {robot_id} (WebSocket): {e}")
                
        elif robot_id in tcp_robots:
            try:
                # Robot kết nối qua TCP
                _, writer = tcp_robots[robot_id]
                writer.write((json.dumps(data) + '\n').encode('utf-8'))
                asyncio.create_task(writer.drain())
                logger.info(f"Đã chuyển tiếp tin nhắn tới robot {robot_id} qua TCP")
                forwarded = True
            except Exception as e:
                logger.error(f"Không thể chuyển tiếp tin nhắn đến robot {robot_id} (TCP): {e}")
        
        if forwarded:
            return {
                "type": "forwarded",
                "robot_id": robot_id,
                "status": "success",
                "message": f"Tin nhắn đã được chuyển tiếp đến robot {robot_id}",
                "timestamp": time.time()
            }
        else:
            return {
                "type": "error",
                "status": "not_forwarded",
                "robot_id": robot_id,
                "message": f"Robot {robot_id} không kết nối hoặc không thể chuyển tiếp tin nhắn",
                "timestamp": time.time()
            }
    
    # Mặc định trả về thông báo nhận được tin nhắn
    return {
        "type": "data_ack",
        "status": "received",
        "message_type": message_type,
        "timestamp": time.time()
    }

async def handle_tcp_client(reader, writer):
    """Xử lý kết nối TCP client"""
    addr = writer.get_extra_info('peername')
    client_id = f"{addr[0]}:{addr[1]}" if addr else "unknown"
    client_robot_id = None  # Track robot ID for this connection
    logger.info(f"[TCP] Kết nối mới từ {client_id}")
    
    try:
        # Gửi tin nhắn chào mừng
        welcome_message = json.dumps({
            "type": "welcome",
            "message": "Connected to TCP server",
            "timestamp": time.time()
        }) + '\n'
        writer.write(welcome_message.encode('utf-8'))
        await writer.drain()
        logger.info(f"[TCP] Đã gửi welcome đến {client_id}: {welcome_message.strip()}")
        
        # Xử lý dữ liệu
        buffer = ""
        while True:
            # Đọc dữ liệu
            data = await reader.read(4096)
            if not data:
                logger.info(f"[TCP] Kết nối đóng từ {client_id}")
                break
                
            # Log dữ liệu raw nhận được
            raw_data = data.decode('utf-8')
            logger.debug(f"[TCP] Nhận raw từ {client_id}: {raw_data}")
                
            # Thêm vào buffer
            buffer += raw_data
            
            # Xử lý từng dòng (tin nhắn)
            while '\n' in buffer:
                message, buffer = buffer.split('\n', 1)
                if not message.strip():
                    continue
                    
                # Log tin nhắn nhận được
                logger.info(f"[TCP] Nhận từ {client_id}: {message}")
                
                try:
                    # Parse JSON
                    data = json.loads(message)
                    
                    # Log loại tin nhắn
                    msg_type = data.get("type", "unknown")
                    robot_id = data.get("robot_id", "unknown")
                    logger.info(f"[TCP] Xử lý tin nhắn từ {client_id}: type={msg_type}, robot_id={robot_id}")
                    
                    # FIX: Handle registration with proper confirmation
                    if msg_type == "registration":
                        # Đăng ký robot
                        client_robot_id = robot_id
                        logger.info(f"[TCP] Đăng ký robot {robot_id} từ {client_id}")
                        
                        # Lưu kết nối TCP robot
                        tcp_robots[robot_id] = (reader, writer)
                        
                        # Lưu thông tin robot
                        robot_data[robot_id] = data
                        
                        # Gửi xác nhận đăng ký - IMPORTANT: Use registration_confirmation
                        response = {
                            "type": "registration_confirmation",  # NOT data_ack
                            "robot_id": robot_id,
                            "status": "success", 
                            "timestamp": time.time()
                        }
                        
                        # Gửi response
                        response_str = json.dumps(response) + '\n'
                        writer.write(response_str.encode('utf-8'))
                        await writer.drain()
                        logger.info(f"[TCP] Đã gửi registration_confirmation đến {client_id}: {response}")
                        
                        # Forward to frontend if connected
                        if frontend_bridge:
                            try:
                                await frontend_bridge.send(json.dumps({
                                    "type": "robot_connected",
                                    "robot_id": robot_id,
                                    "info": data,
                                    "timestamp": time.time()
                                }))
                                logger.info(f"[TCP] Forwarded robot registration to frontend")
                            except Exception as e:
                                logger.error(f"[TCP] Error forwarding registration to frontend: {e}")
                        
                        continue  # Skip normal response handling
                    
                    # FIX: Handle frontend messages
                    if "frontend" in data and robot_id != "unknown":
                        # This is a message from frontend to robot
                        if robot_id in tcp_robots:
                            # Forward to TCP robot
                            _, robot_writer = tcp_robots[robot_id]
                            try:
                                # Forward the message
                                robot_writer.write((json.dumps(data) + '\n').encode('utf-8'))
                                await robot_writer.drain()
                                logger.info(f"[TCP] Forwarded message to robot {robot_id}")
                                
                                # Send acknowledgment
                                response = {
                                    "type": "command_sent",
                                    "robot_id": robot_id,
                                    "status": "success",
                                    "timestamp": time.time()
                                }
                            except Exception as e:
                                logger.error(f"[TCP] Error forwarding to robot {robot_id}: {e}")
                                response = {
                                    "type": "error",
                                    "status": "failed",
                                    "message": f"Error forwarding to robot: {str(e)}",
                                    "timestamp": time.time()
                                }
                        else:
                            # Robot not connected
                            response = {
                                "type": "error",
                                "status": "not_found",
                                "message": f"Robot {robot_id} not connected",
                                "timestamp": time.time()
                            }
                    
                    # FIX: Handle data from robot to frontend
                    elif client_robot_id and msg_type not in ["heartbeat", "ping", "pong"]:
                        # This is data from a registered robot - forward to frontend
                        if frontend_bridge:
                            try:
                                # Forward to frontend
                                await frontend_bridge.send(json.dumps(data))
                                logger.info(f"[TCP] Forwarded {msg_type} from robot {robot_id} to frontend")
                                
                                # Send acknowledgment to robot
                                response = {
                                    "type": "data_ack",
                                    "status": "received",
                                    "message_type": msg_type,
                                    "timestamp": time.time()
                                }
                            except Exception as e:
                                logger.error(f"[TCP] Error forwarding to frontend: {e}")
                                response = {
                                    "type": "error",
                                    "status": "forward_failed",
                                    "message": f"Error forwarding to frontend: {str(e)}",
                                    "timestamp": time.time()
                                }
                        else:
                            # No frontend bridge - just acknowledge
                            response = {
                                "type": "data_ack",
                                "status": "received",
                                "message_type": msg_type,
                                "timestamp": time.time()
                            }
                    else:
                        # Default response for other message types
                        response = {
                            "type": "data_ack",
                            "status": "received",
                            "message_type": msg_type,
                            "timestamp": time.time()
                        }
                    
                    # Send response
                    response_str = json.dumps(response) + '\n'
                    writer.write(response_str.encode('utf-8'))
                    await writer.drain()
                    logger.info(f"[TCP] Sent to {client_id}: {response}")
                    
                except json.JSONDecodeError:
                    logger.error(f"[TCP] Invalid JSON from {client_id}: {message}")
                    # Send error response
                    error_msg = json.dumps({
                        "type": "error",
                        "status": "invalid_json",
                        "message": "Invalid JSON data",
                        "timestamp": time.time()
                    }) + '\n'
                    writer.write(error_msg.encode('utf-8'))
                    await writer.drain()
                except Exception as e:
                    logger.error(f"[TCP] Error processing data from {client_id}: {e}")
                    logger.error(traceback.format_exc())
                    
                    try:
                        # Send error response
                        error_msg = json.dumps({
                            "type": "error",
                            "status": "processing_error",
                            "message": f"Error processing data: {str(e)}",
                            "timestamp": time.time()
                        }) + '\n'
                        writer.write(error_msg.encode('utf-8'))
                        await writer.drain()
                    except:
                        pass
    
    except ConnectionResetError:
        logger.info(f"[TCP] Connection reset by {client_id}")
    except Exception as e:
        logger.error(f"[TCP] Error handling TCP connection from {client_id}: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Clean up
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass
        logger.info(f"[TCP] Connection closed with {client_id}")
        
        # Remove robot from tracking if this was a robot connection
        if client_robot_id and client_robot_id in tcp_robots:
            logger.info(f"[TCP] Removed robot {client_robot_id} from tcp_robots")
            del tcp_robots[client_robot_id]
            
            # Notify frontend that robot disconnected
            if frontend_bridge:
                try:
                    await frontend_bridge.send(json.dumps({
                        "type": "robot_disconnected",
                        "robot_id": client_robot_id,
                        "timestamp": time.time()
                    }))
                except:
                    pass


# Update start_server function to connect to WebSocket Bridge
async def start_server():
    """Start TCP server and connect to WebSocket Bridge"""
    server = await asyncio.start_server(
        handle_tcp_client, 'localhost', 9000
    )
    
    addr = server.sockets[0].getsockname()
    logger.info(f'TCP Server running on {addr[0]}:{addr[1]}')
    
    # Connect to WebSocket Bridge
    asyncio.create_task(connect_to_ws_bridge())
    
    async with server:
        await server.serve_forever()

# Main entry point
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"tcp_server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        ]
    )
    logger = logging.getLogger('tcp_server')
    logger.info("Starting TCP Server...")
    
    # Run server
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        logger.error(traceback.format_exc())