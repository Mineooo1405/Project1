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

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tcp_server.log")
    ]
)

# Thêm các biến để kiểm soát log
import os

# Cài đặt log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip()
LOG_HEARTBEATS = os.environ.get("LOG_HEARTBEATS", "0").strip() == "1" 
LOG_DETAILED_MESSAGES = os.environ.get("LOG_DETAILED_MESSAGES", "0").strip() == "1"
DEBUG_MODE = os.environ.get("DEBUG_MODE", "0").strip() == "1"

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

# Khai báo biến toàn cục
robots = {}  # {robot_id: socket}
backend_connections = {}  # {robot_id: websocket}
frontend_bridge = None  # WebSocket connection to frontend bridge
clients = {}  # {client_id: socket}
clients_lock = threading.Lock()
robots_lock = threading.Lock()

# === BACKEND CONNECTION MANAGEMENT ===

async def connect_to_backend(robot_id):
    """Kết nối đến backend WebSocket cho robot cụ thể"""
    try:
        # Kết nối đến backend API
        backend_uri = f"ws://localhost:8000/ws/robot/{robot_id}"
        websocket = await websockets.connect(backend_uri)
        logger.info(f"Đã kết nối tới backend cho robot {robot_id}")
        return websocket
    except Exception as e:
        logger.error(f"Lỗi kết nối tới backend cho robot {robot_id}: {e}")
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
    """Gửi dữ liệu từ TCP server đến robot"""
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
        logger.info(f"Đã gửi dữ liệu đến robot {robot_id}: {data}")
        return True
    except Exception as e:
        logger.error(f"Lỗi gửi dữ liệu đến robot {robot_id}: {e}")
        
        # Nếu lỗi kết nối, đánh dấu robot đã ngắt kết nối
        if robot_id in robots:
            del robots[robot_id]
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
        
        # Đọc và xử lý dữ liệu từ robot
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
    """Xử lý kết nối WebSocket từ WebSocket Bridge"""
    global frontend_bridge
    frontend_bridge = websocket
    logger.info(f"WebSocket Bridge đã kết nối")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"Nhận thông điệp từ WebSocket Bridge: {data}")
                
                # Thêm kiểm tra và xử lý đặc biệt cho get_robot_connections
                if data.get("type") == "get_robot_connections" and "robot_id" not in data:
                    data["robot_id"] = "robot1"
                    logger.debug(f"Đã tự động thêm robot_id=robot1 vào lệnh get_robot_connections")
                
                # Xử lý thông điệp từ frontend
                response = handle_frontend_message(data)
                
                # Gửi phản hồi về WebSocket Bridge
                await websocket.send(json.dumps(response))
                
            except json.JSONDecodeError:
                logger.error(f"Dữ liệu JSON không hợp lệ từ WebSocket Bridge: {message}")
            except Exception as e:
                logger.error(f"Lỗi xử lý thông điệp từ WebSocket Bridge: {e}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "status": "error",
                    "message": f"Lỗi xử lý thông điệp: {str(e)}",
                    "timestamp": time.time()
                }))
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"WebSocket Bridge đã ngắt kết nối")
    finally:
        frontend_bridge = None

async def start_server(host='0.0.0.0', port=9000, ws_port=9002):
    """Khởi động TCP server và WebSocket server"""
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
    
    # Giữ async event loop chạy
    try:
        await asyncio.Future()  # Chạy mãi mãi
    finally:
        server.close()
        ws_server.close()

# Entry point
if __name__ == "__main__":
    logger.info("Khởi động TCP Server...")
    asyncio.run(start_server())

# Trong hàm handle_data hoặc process_message, thêm xử lý cho các loại yêu cầu mới

def handle_data(client_socket, client_id, robot_id, data):
    """Xử lý dữ liệu từ client"""
    data_type = data.get("type", "unknown")
    
    # Kiểm tra nếu là heartbeat hoặc các loại thông điệp thường xuyên
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
                        # Thêm điện thoại vào danh sách, gán tạm là robot1 nếu chưa xác định
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
            logger.debug(f"Đã tự động thêm robot_id=robot1 vào lệnh get_robot_connections")
        
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
                "robot_id": data.get("robot_id", "robot1"),  # Sử dụng robot_id từ request hoặc mặc định
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
        
        # Đóng socket và xóa khỏi danh sách
        try:
            client_socket.close()
        except:
            pass
        
        with clients_lock:
            if client_id in clients:
                del clients[client_id]

# Hàm kiểm tra nếu là heartbeat message
def is_heartbeat_message(data):
    """Kiểm tra nếu thông điệp là heartbeat hoặc get_robot_connections"""
    if isinstance(data, dict):
        message_type = data.get("type", "")
        return message_type in ["heartbeat", "get_robot_connections", "ping", "status"]
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

# Thêm hoặc cập nhật hàm xử lý connect_robot_simulator
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