import asyncio
import websockets
import json
import socket
import threading
import logging
import time
import os
from datetime import datetime
import traceback

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(), 
        logging.FileHandler(f"ws_bridge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
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
    """Client for connecting to TCP server"""
    
    def __init__(self, host='localhost', port=9000):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.buffer = ""  # Add buffer for partial messages
        self.lock = asyncio.Lock()  # Thêm lock để tránh nhiều thread gửi cùng lúc
        self.timeout = 3.0  # Timeout 3 giây cho các thao tác socket
    
    def connect(self):
        """Kết nối đến TCP server"""
        if self.connected:
            return True
            
        try:
            logger.info(f"Đang kết nối đến TCP server ({self.host}:{self.port})...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setblocking(False)  # Non-blocking socket
            self.socket.settimeout(self.timeout)  # Timeout 3 giây
            self.socket.connect((self.host, self.port))
            self.connected = True
            self.buffer = ''
            
            # Đọc thông điệp chào mừng
            try:
                welcome_data = self.socket.recv(4096)
                if welcome_data:
                    welcome_msg = welcome_data.decode('utf-8').strip()
                    # Cố gắng parse JSON nếu có thể
                    try:
                        json_msg = json.loads(welcome_msg)
                        logger.info(f"Đã kết nối đến TCP server: {json_msg}")
                    except json.JSONDecodeError:
                        logger.info(f"Đã kết nối đến TCP server: {welcome_msg}")
            except socket.timeout:
                logger.info("Đã kết nối đến TCP server (không có thông điệp chào)")
            
            return True
        except Exception as e:
            logger.error(f"Không thể kết nối đến TCP server: {e}")
            self.connected = False
            self.socket = None
            return False
    
    def send_command(self, command):
        """Gửi lệnh đến TCP server và trả về kết quả"""
        try:
            if not self.connected:
                if not self.connect():
                    return {"status": "error", "message": "Không thể kết nối đến TCP server"}
            
            # Đảm bảo command là dictionary
            if not isinstance(command, dict):
                command = {"command": str(command)}
            
            # Thêm timestamp nếu chưa có
            if "timestamp" not in command:
                command["timestamp"] = time.time()
                
            # Thêm robot_id nếu chưa có
            if "robot_id" not in command:
                command["robot_id"] = "websocket_bridge"
                logger.warning(f"Đã thêm robot_id thiếu vào lệnh {command.get('type', 'unknown')}")
            
            # Chuyển đổi thành JSON string và thêm newline
            command_str = json.dumps(command) + '\n'
            
            # Gửi lệnh với timeout
            self.socket.settimeout(3.0)  # 3 giây timeout
            start_time = time.time()
            self.socket.sendall(command_str.encode('utf-8'))
            elapsed = time.time() - start_time
            
            logger.info(f"Đã gửi đến TCP server: {command} (thời gian gửi: {elapsed:.4f}s)")
            
            # Đọc phản hồi từ server (nếu có)
            try:
                response_data = self.socket.recv(4096)
                if response_data:
                    try:
                        response = json.loads(response_data.decode('utf-8'))
                        logger.info(f"Nhận phản hồi từ TCP server: {response}")
                        return response
                    except json.JSONDecodeError:
                        logger.warning(f"Phản hồi không hợp lệ từ TCP server: {response_data}")
            except socket.timeout:
                logger.debug("Không có phản hồi từ TCP server (timeout)")
            
            # Mặc định trả về tin nhắn đã gửi
            return {"status": "sent", "message": "Đã gửi lệnh đến TCP server"}
            
        except socket.timeout:
            logger.error(f"Timeout khi gửi lệnh đến TCP server")
            self.connected = False
            return {"status": "error", "message": "Timeout khi gửi lệnh đến TCP server"}
        except Exception as e:
            logger.error(f"Lỗi gửi lệnh đến TCP server: {e}")
            self.connected = False
            return {"status": "error", "message": f"Lỗi gửi lệnh: {str(e)}"}
    
    def disconnect(self):
        """Disconnect from TCP server"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.connected = False
            logger.info("Disconnected from TCP server")

# Thêm đoạn mã này sau khi định nghĩa lớp TCPClient và trước hàm handle_websocket
# Khởi tạo đối tượng TCP client global
tcp_client = TCPClient()

# Hàm kết nối lại TCP client nếu mất kết nối
def ensure_tcp_connection():
    """Đảm bảo có kết nối với TCP server"""
    if tcp_client.connected:
        return True
        
    # Thử kết nối
    if tcp_client.connect():
        return True
    
    # Thử lại một lần nữa sau 1 giây
    logger.warning("Kết nối thất bại, thử lại sau 1 giây")
    time.sleep(1)
    
    return tcp_client.connect()

# Thêm sau hàm ensure_tcp_connection

async def listen_to_tcp_messages():
    """Lắng nghe và xử lý tin nhắn từ TCP server"""
    while True:
        try:
            if not tcp_client.connected:
                if not ensure_tcp_connection():
                    # Nếu không thể kết nối, đợi một lúc rồi thử lại
                    await asyncio.sleep(5)
                    continue
            
            # Thiết lập socket non-blocking
            tcp_client.socket.settimeout(0.1)
            
            # Đọc dữ liệu từ TCP server
            try:
                data = tcp_client.socket.recv(4096)
                if not data:
                    logger.warning("TCP server đã đóng kết nối")
                    tcp_client.connected = False
                    continue
                
                # Thêm dữ liệu vào buffer
                tcp_client.buffer += data.decode('utf-8')
                
                # Xử lý các dòng hoàn chỉnh
                while '\n' in tcp_client.buffer:
                    line, tcp_client.buffer = tcp_client.buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    
                    try:
                        message = json.loads(line)
                        logger.info(f"Nhận từ TCP server: {message}")
                        
                        # Broadcast message đến tất cả clients
                        await broadcast_to_clients(message)
                        
                    except json.JSONDecodeError:
                        logger.error(f"Dữ liệu không hợp lệ từ TCP server: {line}")
                
            except socket.timeout:
                # Timeout là bình thường trong non-blocking mode
                pass
            except ConnectionResetError:
                logger.error("Kết nối TCP server đã bị đặt lại")
                tcp_client.connected = False
            except Exception as e:
                logger.error(f"Lỗi khi nhận dữ liệu từ TCP server: {e}")
                tcp_client.connected = False
        
        except Exception as e:
            logger.error(f"Lỗi trong listen_to_tcp_messages: {e}")
        
        # Ngủ một chút để tránh CPU cao
        await asyncio.sleep(0.1)

# Thêm hàm này trước hàm handle_websocket

async def broadcast_to_clients(message):
    """
    Gửi thông điệp đến tất cả clients WebSocket
    
    Args:
        message (dict): Thông điệp cần gửi
    """
    if not clients:
        # Không có clients kết nối
        return
    
    # Nếu là heartbeat và không cần log heartbeat
    is_heartbeat = is_heartbeat_message(message)
    if is_heartbeat and not LOG_HEARTBEATS:
        return  # Bỏ qua không gửi heartbeat nếu không cần log
    
    # Thử gửi đến từng client
    disconnected_clients = []
    
    for client_id, websocket in clients.items():
        try:
            await websocket.send(json.dumps(message))
            
            # Log gửi thành công nếu không phải heartbeat hoặc LOG_HEARTBEATS=True
            if not is_heartbeat or LOG_HEARTBEATS:
                conditional_log("DEBUG", f"Đã gửi đến client {client_id}: {message}", is_heartbeat)
                
        except websockets.exceptions.ConnectionClosed:
            # Client đã ngắt kết nối
            conditional_log("INFO", f"Client {client_id} đã ngắt kết nối")
            disconnected_clients.append(client_id)
        except Exception as e:
            # Lỗi khác
            conditional_log("ERROR", f"Lỗi gửi đến client {client_id}: {e}")
            disconnected_clients.append(client_id)
    
    # Xóa các clients đã ngắt kết nối
    for client_id in disconnected_clients:
        if client_id in clients:
            del clients[client_id]

# Cải thiện xử lý thông điệp từ WebSocket
clients = {}
tcp_server = None  # TCP server connection

# Sửa hàm xử lý WebSocket để đảm bảo các lệnh từ frontend được chuyển tiếp đúng cách
async def handle_websocket(websocket, path):
    """
    Xử lý kết nối WebSocket từ frontend
    """
    client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    logger.info(f"[WS] Kết nối mới từ {client_id} trên path {path}")
    
    # Special handling for TCP server connection
    if path == "/tcp_server":
        logger.info(f"[WS] TCP Server connected via WebSocket")
        global tcp_server
        tcp_server = websocket
        
        try:
            # Handle messages from TCP server
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.info(f"[WS] Received from TCP server: {data.get('type')}")
                    
                    # Forward messages to all connected clients
                    for client_ws in clients.values():
                        try:
                            await client_ws.send(message)
                        except:
                            pass
                except Exception as e:
                    logger.error(f"[WS] Error processing TCP server message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("[WS] TCP Server WebSocket connection closed")
        finally:
            # Reset TCP server connection
            if tcp_server == websocket:
                tcp_server = None
        
        return
    
    # Regular client connection
    clients[client_id] = websocket
    
    # Đảm bảo có kết nối TCP
    ensure_tcp_connection()
    
    try:
        # Gửi welcome message
        welcome_msg = {
            "type": "heartbeat", 
            "robot_id": "websocket_bridge",
            "source": "ws_bridge",
            "timestamp": time.time()
        }
        await websocket.send(json.dumps(welcome_msg))
        logger.info(f"[WS] Đã gửi welcome đến client {client_id}")
        
        # Xử lý tin nhắn từ client
        async for message_text in websocket:
            try:
                # Parse tin nhắn JSON
                message = json.loads(message_text)
                
                # Thêm timestamp nếu chưa có
                if "timestamp" not in message:
                    message["timestamp"] = time.time()
                
                # Đảm bảo có robot_id
                if "robot_id" not in message:
                    message["robot_id"] = "unknown"
                    logger.warning(f"[WS] Tin nhắn không có robot_id: {message}")
                
                # Thêm frontend flag để server biết nguồn tin nhắn
                if "frontend" not in message:
                    message["frontend"] = True
                
                # Debug log detailed information
                logger.info(f"[WS] Nhận từ frontend (client {client_id}): {message}")
                
                # Two paths for message forwarding:
                # 1. If TCP server is connected via WebSocket, use that
                # 2. Otherwise use TCP socket
                
                if tcp_server:
                    # 1. Forward via WebSocket connection
                    try:
                        await tcp_server.send(json.dumps(message))
                        logger.info(f"[WS] Forwarded message to TCP server via WebSocket")
                    except Exception as e:
                        logger.error(f"[WS] Error forwarding to TCP server via WebSocket: {e}")
                        # Fall back to TCP socket
                        if ensure_tcp_connection():
                            tcp_client.socket.sendall((json.dumps(message) + "\n").encode("utf-8"))
                            logger.info(f"[WS] Forwarded message to TCP server via socket (fallback)")
                        else:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "status": "server_unreachable",
                                "message": "TCP Server is unreachable",
                                "timestamp": time.time()
                            }))
                else:
                    # 2. Forward via TCP socket
                    if ensure_tcp_connection():
                        try:
                            tcp_client.socket.sendall((json.dumps(message) + "\n").encode("utf-8"))
                            logger.info(f"[WS] Forwarded message to TCP server via socket")
                            
                            # Read response from TCP server
                            try:
                                tcp_client.socket.settimeout(3)
                                response_data = tcp_client.socket.recv(4096)
                                if response_data:
                                    response_text = response_data.decode("utf-8")
                                    tcp_client.buffer += response_text
                                    
                                    # Process complete messages
                                    while "\n" in tcp_client.buffer:
                                        line, tcp_client.buffer = tcp_client.buffer.split("\n", 1)
                                        if not line.strip():
                                            continue
                                            
                                        try:
                                            response = json.loads(line)
                                            logger.info(f"[WS] Response from TCP server: {response}")
                                            
                                            # Forward to client
                                            await websocket.send(json.dumps(response))
                                            logger.info(f"[WS] Forwarded response to client {client_id}")
                                        except json.JSONDecodeError:
                                            logger.error(f"[WS] Invalid JSON response: {line}")
                            except socket.timeout:
                                logger.info("[WS] No response from TCP server (timeout)")
                            except Exception as e:
                                logger.error(f"[WS] Error receiving TCP response: {e}")
                        except Exception as e:
                            logger.error(f"[WS] Error sending to TCP server: {e}")
                            await websocket.send(json.dumps({
                                "type": "error",
                                "status": "send_error",
                                "message": f"Error sending to TCP server: {str(e)}",
                                "timestamp": time.time()
                            }))
                    else:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "status": "server_unreachable",
                            "message": "TCP Server is unreachable",
                            "timestamp": time.time()
                        }))
                
            except json.JSONDecodeError:
                logger.error(f"[WS] Dữ liệu không hợp lệ từ client {client_id}: {message_text}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "status": "invalid_json",
                    "message": "Định dạng JSON không hợp lệ",
                    "timestamp": time.time()
                }))
            except Exception as e:
                logger.error(f"[WS] Lỗi xử lý tin nhắn từ client {client_id}: {e}")
                try:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "status": "processing_error",
                        "message": f"Lỗi xử lý tin nhắn: {str(e)}",
                        "timestamp": time.time()
                    }))
                except:
                    pass
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"[WS] Client {client_id} đã ngắt kết nối")
    except Exception as e:
        logger.error(f"[WS] Lỗi xử lý WebSocket connection: {e}")
    finally:
        if client_id in clients:
            del clients[client_id]

# Cải tiến hàm send_tcp_command_async
async def send_tcp_command_async(message):
    """Gửi lệnh đến TCP server bất đồng bộ với timing"""
    # Lưu thời gian bắt đầu
    start_time = time.time()
    logger.info(f"Bắt đầu gửi tin nhắn đến TCP server: {message.get('type')}")
    
    # Chạy send_command trong một thread riêng để tránh blocking
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, tcp_client.send_command, message)
        
        # Tính thời gian gửi
        elapsed = time.time() - start_time
        logger.info(f"Thời gian gửi tin nhắn đến TCP server: {elapsed:.4f} giây")
        
        return result
    except Exception as e:
        # Tính thời gian thất bại
        elapsed = time.time() - start_time
        logger.error(f"Lỗi gửi tin nhắn đến TCP server sau {elapsed:.4f} giây: {e}")
        raise e

async def send_heartbeat():
    """
    Gửi tin nhắn heartbeat định kỳ đến TCP server để duy trì kết nối
    """
    while True:
        try:
            if ensure_tcp_connection():
                # Tạo tin nhắn heartbeat với robot_id mặc định
                heartbeat = {
                    "type": "heartbeat",
                    "robot_id": "websocket_bridge",  # Thêm robot_id
                    "source": "ws_bridge",           # Thêm source để dễ phân biệt
                    "timestamp": time.time()
                }
                
                # Gửi đến TCP server
                tcp_client.send_command(heartbeat)
                
                # Gửi đến tất cả các clients đang kết nối
                for client_id, websocket in clients.items():
                    try:
                        await websocket.send(json.dumps(heartbeat))
                    except Exception as e:
                        logger.error(f"Lỗi gửi heartbeat đến client {client_id}: {e}")
                
                logger.debug(f"Đã gửi heartbeat đến TCP server và clients")
            
            # Đợi cho đến lần gửi tiếp theo
            await asyncio.sleep(30)  # Gửi heartbeat mỗi 30 giây
            
        except Exception as e:
            logger.error(f"Lỗi trong quá trình gửi heartbeat: {e}")
            await asyncio.sleep(10)  # Đợi 10 giây nếu có lỗi

async def send_to_tcp(message):
    """Gửi tin nhắn đến TCP server"""
    # This function is not being used in the current implementation
    # We're using TCPClient class instead
    logger.warning("send_to_tcp is deprecated, use tcp_client.send_command instead")
    
    if tcp_client.connected:
        return tcp_client.send_command(message)
    else:
        if ensure_tcp_connection():
            return tcp_client.send_command(message)
        else:
            return {
                "type": "error",
                "status": "connection_error",
                "message": "Không thể kết nối đến TCP server",
                "timestamp": time.time()
            }
            
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
    
    # Khởi động task lắng nghe tin nhắn từ TCP server
    tcp_listener_task = asyncio.create_task(listen_to_tcp_messages())
    
    # Khởi động task heartbeat
    heartbeat_task = asyncio.create_task(send_heartbeat())
    
    # Khởi động task xử lý tin nhắn từ TCP server
    tcp_message_handler_task = asyncio.create_task(handle_tcp_messages())
    
    logger.info(f"WebSocket-TCP Bridge đã khởi động trên {host}:{port}")
    await asyncio.Future()  # Chạy mãi mãi

def ensure_robot_id(message, default_id="websocket_bridge"):
    """
    Đảm bảo tin nhắn có trường robot_id
    
    Args:
        message: Dict tin nhắn cần kiểm tra
        default_id: ID mặc định nếu không có robot_id
        
    Returns:
        Dict tin nhắn đã có robot_id
    """
    # Nếu message không phải dict, chuyển thành dict
    if not isinstance(message, dict):
        try:
            # Thử parse JSON nếu là string
            if isinstance(message, str):
                message = json.loads(message)
            else:
                # Nếu không phải string, tạo dict mới
                message = {"data": str(message)}
        except:
            message = {"data": str(message)}
    
    # Thêm robot_id nếu chưa có
    if "robot_id" not in message:
        message["robot_id"] = default_id
        logger.warning(f"Đã thêm robot_id thiếu vào lệnh {message.get('type', 'unknown')}")
    
    # Đảm bảo có timestamp
    if "timestamp" not in message:
        message["timestamp"] = time.time()
    
    return message

# Add/update the handle_tcp_messages function
async def handle_tcp_messages():
    """Handle messages from TCP server to forward to WebSocket clients"""
    logger.info("Bắt đầu xử lý tin nhắn từ TCP server")
    
    while True:
        try:
            # Ensure we have a connection
            if not tcp_client.connected:
                tcp_client.connect()
                await asyncio.sleep(1)
                continue
                
            # Try to read from socket
            try:
                tcp_client.socket.settimeout(0.1)
                data = tcp_client.socket.recv(4096)
                
                if not data:
                    logger.warning("TCP Server closed connection")
                    tcp_client.disconnect()
                    await asyncio.sleep(1)
                    continue
                    
                # Add to buffer and process
                tcp_client.buffer += data.decode('utf-8')
                
                # Process complete messages
                while '\n' in tcp_client.buffer:
                    message, tcp_client.buffer = tcp_client.buffer.split('\n', 1)
                    if not message.strip():
                        continue
                        
                    try:
                        data = json.loads(message)
                        logger.info(f"Nhận từ TCP server: {data}")
                        
                        # Forward to all WebSocket clients
                        for client_id, websocket in list(clients.items()):
                            try:
                                await websocket.send(json.dumps(data))
                                logger.info(f"Đã chuyển tiếp tin nhắn đến client {client_id}")
                            except Exception as e:
                                logger.error(f"Lỗi chuyển tiếp đến client {client_id}: {e}")
                                # Client might be disconnected
                                if client_id in clients:
                                    del clients[client_id]
                    except json.JSONDecodeError:
                        logger.error(f"Dữ liệu không hợp lệ từ TCP server: {message}")
                    
            except socket.timeout:
                # This is expected for non-blocking
                pass
            except ConnectionResetError:
                logger.warning("Kết nối TCP server bị đặt lại")
                tcp_client.disconnect()
            except Exception as e:
                logger.error(f"Lỗi đọc tin nhắn từ TCP server: {e}")
                tcp_client.disconnect()
                
            await asyncio.sleep(0.01)  # Small sleep to prevent CPU hogging
            
        except Exception as e:
            logger.error(f"Lỗi xử lý tin nhắn từ TCP server: {e}")
            await asyncio.sleep(1)

# Start WebSocket server
async def start_server():
    """Start WebSocket server"""
    server = await websockets.serve(
        handle_websocket, "localhost", 9003
    )
    
    logger.info(f"WebSocket Bridge running on localhost:9003")
    
    # Keep server running
    await server.wait_closed()

# TCP messages listener
async def tcp_listener():
    """Listen for messages from TCP server and forward to clients"""
    while True:
        if tcp_client.connected and tcp_client.socket:
            try:
                tcp_client.socket.settimeout(0.1)
                data = tcp_client.socket.recv(4096)
                if data:
                    # Add to buffer
                    tcp_client.buffer += data.decode("utf-8")
                    
                    # Process complete messages
                    while "\n" in tcp_client.buffer:
                        message, tcp_client.buffer = tcp_client.buffer.split("\n", 1)
                        if not message.strip():
                            continue
                            
                        try:
                            data = json.loads(message)
                            logger.info(f"[TCP] Received: {data.get('type')}")
                            
                            # Forward to all clients
                            for client_id, client in clients.items():
                                try:
                                    await client.send(json.dumps(data))
                                    logger.info(f"[TCP] Forwarded to client {client_id}")
                                except Exception as e:
                                    logger.error(f"[TCP] Error forwarding to client {client_id}: {e}")
                        except json.JSONDecodeError:
                            logger.error(f"[TCP] Invalid JSON: {message}")
                        except Exception as e:
                            logger.error(f"[TCP] Processing error: {e}")
                            
            except socket.timeout:
                # Expected for non-blocking
                pass
            except ConnectionResetError:
                logger.error("[TCP] Connection reset by server")
                tcp_client.disconnect()
            except Exception as e:
                logger.error(f"[TCP] Listener error: {e}")
                tcp_client.disconnect()
        else:
            # Try to reconnect
            if not tcp_client.connected:
                tcp_client.connect()
        
        # Yield to other tasks
        await asyncio.sleep(0.1)

# Main function
async def main():
    """Start WebSocket Bridge and TCP listener"""
    # Start TCP listener
    asyncio.create_task(tcp_listener())
    
    # Start WebSocket server
    await start_server()

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