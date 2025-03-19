from fastapi import FastAPI, WebSocket, WebSocketDisconnect, APIRouter
from typing import Dict, List, Any
import json
import asyncio
import time
from pydantic import BaseModel
import logging

# Thiết lập logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Khởi tạo router
router = APIRouter()

# Theo dõi kết nối WebSocket
ws_connections = {
    "motor": [],
    "pid": [],
    "trajectory": [],
    "firmware": [],
    "server": []
}

# Lưu trữ thống kê kết nối
connection_stats = {
    "total_connections": 0,
    "messages_received": 0,
    "messages_sent": 0,
    "last_activity": time.time()
}

# Class để lưu thông tin kết nối
class WebSocketConnection:
    def __init__(self, ws: WebSocket, client_id: str = None):
        self.ws = ws
        self.client_id = client_id or f"client_{id(ws)}"
        self.connected_at = time.time()
        self.last_activity = time.time()
        self.message_count = 0
    
    def update_activity(self):
        self.last_activity = time.time()
        self.message_count += 1
        connection_stats["last_activity"] = time.time()


# API endpoint để lấy trạng thái kết nối
@router.get("/api/connection-status")
async def get_connection_status():
    return {
        "status": "running",
        "active_connections": {
            "motor": len(ws_connections["motor"]),
            "pid": len(ws_connections["pid"]),
            "trajectory": len(ws_connections["trajectory"]),
            "firmware": len(ws_connections["firmware"]),
            "server": len(ws_connections["server"])
        },
        "stats": {
            "total_connections": connection_stats["total_connections"],
            "messages_received": connection_stats["messages_received"],
            "messages_sent": connection_stats["messages_sent"],
            "last_activity": connection_stats["last_activity"]
        }
    }


# Xử lý tin nhắn đến
async def handle_message(ws: WebSocket, data: dict, endpoint: str, connection: WebSocketConnection):
    """Xử lý tin nhắn đến từ client qua WebSocket"""
    msg_type = data.get("type", "unknown")
    connection.update_activity()
    connection_stats["messages_received"] += 1
    
    logger.info(f"Received {msg_type} message on {endpoint} from {connection.client_id}")
    
    # Xử lý các loại tin nhắn khác nhau
    if msg_type == "echo":
        # Phản hồi echo với tin nhắn gốc
        response = {
            "type": "echo_response",
            "original_message": data,
            "server_time": time.time(),
            "request_id": data.get("id"),
            "test_id": data.get("test_id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    elif msg_type == "ping":
        # Phản hồi với pong
        response = {
            "type": "pong",
            "timestamp": time.time(),
            "request_id": data.get("id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    elif msg_type == "roundtrip_test":
        # Phản hồi test roundtrip
        response = {
            "type": "roundtrip_response",
            "server_time": time.time(),
            "client_time": data.get("timestamp"),
            "request_id": data.get("id"),
            "test_id": data.get("test_id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    elif msg_type == "query":
        # Xử lý các truy vấn thông tin
        target = data.get("target", "unknown")
        
        if target == "status":
            # Gửi thông tin trạng thái
            response = {
                "type": "status_response",
                "status": "ok",
                "connections": {k: len(v) for k, v in ws_connections.items()},
                "request_id": data.get("id")
            }
            await ws.send_text(json.dumps(response))
            connection_stats["messages_sent"] += 1
            
        elif target == "test_broadcast":
            # Broadcast tin nhắn tới tất cả client trên cùng endpoint
            broadcast_msg = {
                "type": "broadcast",
                "source": connection.client_id,
                "message": "Test broadcast message",
                "timestamp": time.time(),
                "original_request_id": data.get("id")
            }
            # Broadcast tin nhắn
            await broadcast_message(endpoint, broadcast_msg)
    
    elif msg_type == "motor_control":
        # Giả lập xử lý điều khiển động cơ
        motor_id = data.get("motor_id", 0)
        speed = data.get("speed", 0)
        
        # Phản hồi với thông tin động cơ
        response = {
            "type": "motor_status",
            "motor_id": motor_id,
            "current_speed": speed,
            "timestamp": time.time(),
            "request_id": data.get("id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    elif msg_type == "pid_update":
        # Giả lập xử lý cập nhật PID
        response = {
            "type": "pid_status",
            "values": {
                "p": data.get("p", 0),
                "i": data.get("i", 0),
                "d": data.get("d", 0)
            },
            "timestamp": time.time(),
            "request_id": data.get("id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    elif msg_type == "trajectory_request":
        # Giả lập gửi dữ liệu quỹ đạo
        points = []
        num_points = data.get("points", 10)
        
        # Tạo một số điểm giả
        for i in range(num_points):
            points.append({
                "x": i * 0.1,
                "y": (i * 0.1) ** 2,
                "z": (i * 0.1) ** 0.5
            })
        
        response = {
            "type": "trajectory_data",
            "points": points,
            "timestamp": time.time(),
            "request_id": data.get("id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    elif msg_type == "firmware_status":
        # Giả lập dữ liệu firmware
        response = {
            "type": "firmware_info",
            "version": "v2.1.0",
            "build_date": "2023-07-15",
            "status": "up-to-date",
            "request_id": data.get("id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1
    
    else:
        # Loại tin nhắn không xác định
        logger.warning(f"Unknown message type: {msg_type} on {endpoint}")
        response = {
            "type": "error",
            "error": "unknown_message_type",
            "message": f"Message type '{msg_type}' is not supported",
            "request_id": data.get("id")
        }
        await ws.send_text(json.dumps(response))
        connection_stats["messages_sent"] += 1


# Broadcast tin nhắn tới các client
async def broadcast_message(endpoint: str, message: dict):
    """Gửi tin nhắn tới tất cả các kết nối trên endpoint cụ thể"""
    if endpoint not in ws_connections:
        return
    
    connections = ws_connections[endpoint]
    message_json = json.dumps(message)
    
    for conn in connections:
        try:
            await conn.ws.send_text(message_json)
            connection_stats["messages_sent"] += 1
            conn.update_activity()
        except Exception as e:
            logger.error(f"Error broadcasting to {conn.client_id}: {str(e)}")


# Định nghĩa các WebSocket handlers cho các endpoint khác nhau
@router.websocket("/ws/motor")
async def websocket_motor(websocket: WebSocket):
    await handle_websocket(websocket, "motor")

@router.websocket("/ws/pid")
async def websocket_pid(websocket: WebSocket):
    await handle_websocket(websocket, "pid")

@router.websocket("/ws/trajectory")
async def websocket_trajectory(websocket: WebSocket):
    await handle_websocket(websocket, "trajectory")

@router.websocket("/ws/firmware")
async def websocket_firmware(websocket: WebSocket):
    await handle_websocket(websocket, "firmware")

@router.websocket("/ws/server")
async def websocket_server(websocket: WebSocket):
    await handle_websocket(websocket, "server")


# Generic handler cho tất cả các WebSocket endpoints
async def handle_websocket(websocket: WebSocket, endpoint_name: str):
    await websocket.accept()
    
    # Tạo đối tượng kết nối mới
    connection = WebSocketConnection(websocket)
    connection_stats["total_connections"] += 1
    
    # Lưu kết nối vào danh sách
    if endpoint_name in ws_connections:
        ws_connections[endpoint_name].append(connection)
    
    # Gửi thông báo kết nối thành công
    await websocket.send_text(json.dumps({
        "type": "connection_established",
        "client_id": connection.client_id,
        "endpoint": f"/ws/{endpoint_name}",
        "timestamp": time.time()
    }))
    
    logger.info(f"New connection on /ws/{endpoint_name}: {connection.client_id}")
    
    # Bắt đầu task heartbeat
    heartbeat_task = asyncio.create_task(send_heartbeat(websocket, connection))
    
    try:
        # Vòng lặp xử lý tin nhắn chính
        while True:
            # Chờ tin nhắn từ client
            data = await websocket.receive_text()
            
            try:
                json_data = json.loads(data)
                await handle_message(websocket, json_data, f"/ws/{endpoint_name}", connection)
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from {connection.client_id}: {data[:100]}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "error": "invalid_json",
                    "message": "Could not parse JSON message"
                }))
            
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {connection.client_id} from /ws/{endpoint_name}")
        
        # Xóa kết nối khỏi danh sách
        if endpoint_name in ws_connections:
            ws_connections[endpoint_name] = [
                conn for conn in ws_connections[endpoint_name] 
                if conn.client_id != connection.client_id
            ]
        
        # Huỷ task heartbeat
        heartbeat_task.cancel()
    
    except Exception as e:
        logger.error(f"WebSocket error on /ws/{endpoint_name}: {str(e)}")
        heartbeat_task.cancel()


# Heartbeat để giữ kết nối
async def send_heartbeat(ws: WebSocket, connection: WebSocketConnection, interval: int = 30):
    """Gửi tin nhắn heartbeat định kỳ để giữ kết nối"""
    try:
        while True:
            await asyncio.sleep(interval)
            await ws.send_text(json.dumps({
                "type": "ping",
                "timestamp": time.time()
            }))
            connection_stats["messages_sent"] += 1
            
            # Kiểm tra kết nối không hoạt động
            if time.time() - connection.last_activity > interval * 2:
                logger.warning(f"Connection {connection.client_id} inactive for too long")
    
    except asyncio.CancelledError:
        logger.debug(f"Heartbeat task cancelled for {connection.client_id}")
    except Exception as e:
        logger.error(f"Error in heartbeat: {str(e)}")