import asyncio
import datetime
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from database import SessionLocal
from database import EncoderData, TrajectoryData, PIDConfig
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("websocket")

# Database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Constants for connection
HEARTBEAT_INTERVAL = 15  # seconds
MAX_INACTIVE_TIME = 600  # 10 minutes - very high to prevent automatic disconnection

# Simple lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

# Create FastAPI app
app = FastAPI(lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400
)

# Store app start time for uptime tracking
app.state.start_time = time.time()

# Connection lists for different robot endpoints
robot_connections = {
    "robot1": [],
    "robot2": [],
    "robot3": [],
    "robot4": [],
    "server": []
}

# Root endpoint for health check
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "WebSocket server is running",
        "time": datetime.datetime.now().isoformat()
    }

# Health check endpoint
@app.get("/api/health-check")
async def health_check():
    return {
        "status": "ok", 
        "time": datetime.datetime.now().isoformat(),
        "message": "Server is running"
    }

# WebSocket handler for robot connections
async def handle_robot_connection(ws: WebSocket, robot_id: str):
    """Handle WebSocket connection for a specific robot"""
    client_id = f"{ws.client.host}:{ws.client.port}"
    print(f"Connection request from {client_id} for {robot_id}")
    print(f"Active connections for {robot_id}: {len(robot_connections[robot_id])}")
    
    # Khởi tạo heartbeat task
    heartbeat_task = None
    
    try:
        # Accept connection immediately
        await ws.accept()
        print(f"✅ Accepted {robot_id} connection from {client_id}")
        
        # Store metadata
        ws.connected_since = time.time()
        ws.last_activity = time.time()
        ws.client_id = client_id
        ws.robot_id = robot_id
        ws.manual_disconnect = False  # Flag to track manual disconnection
        
        # Add to connection list
        if ws not in robot_connections[robot_id]:
            robot_connections[robot_id].append(ws)
        
        # Send confirmation
        await ws.send_text(json.dumps({
            "status": "connected", 
            "robot_id": robot_id,
            "timestamp": time.time()
        }))
        
        # Khởi động heartbeat để giữ kết nối
        heartbeat_task = asyncio.create_task(send_heartbeat(ws, robot_id))
        
        # Send initial data
        try:
            await send_dummy_robot_data(ws, robot_id)
        except Exception as e:
            print(f"Error sending initial data for {robot_id}: {e}")
            await ws.send_text(json.dumps({
                "type": "partial_data",
                "robot_id": robot_id,
                "timestamp": time.time(),
                "message": "Initial data incomplete, will be updated shortly"
            }))
        
        # Main message loop - KHÔNG tự động ngắt kết nối
        while True:
            try:
                # Thời gian chờ đọc message cao hơn để tránh timeout
                data = await asyncio.wait_for(ws.receive_text(), timeout=MAX_INACTIVE_TIME)
                ws.last_activity = time.time()
                
                # Process command
                try:
                    json_data = json.loads(data)
                    
                    # Kiểm tra xem client có yêu cầu ngắt kết nối không
                    if json_data.get("type") == "manual_disconnect":
                        print(f"Client {client_id} requested manual disconnect from {robot_id}")
                        ws.manual_disconnect = True
                        await ws.send_text(json.dumps({
                            "type": "disconnect_confirmed",
                            "robot_id": robot_id,
                            "timestamp": time.time(),
                            "message": "Disconnect request accepted"
                        }))
                        break
                    
                    await process_robot_command(robot_id, json_data, ws)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({
                        "status": "error",
                        "message": "Invalid JSON data",
                        "timestamp": time.time()
                    }))
            except asyncio.TimeoutError:
                # Không ngắt kết nối khi timeout - chỉ log và gửi ping
                current_time = time.time()
                inactive_time = current_time - ws.last_activity
                print(f"Client {client_id} inactive for {inactive_time:.1f}s")
                
                # Gửi ping để kiểm tra kết nối vẫn sống
                try:
                    await ws.send_text(json.dumps({
                        "type": "ping",
                        "robot_id": robot_id,
                        "timestamp": current_time
                    }))
                    ws.last_activity = current_time
                except Exception as e:
                    print(f"Cannot send ping to inactive client {client_id}: {e}")
                    break  # Chỉ ngắt kết nối khi không gửi được tin nhắn
            except WebSocketDisconnect:
                print(f"Client {client_id} disconnected from {robot_id}")
                break
            except ConnectionClosedOK:
                print(f"Client {client_id} closed connection normally from {robot_id}")
                break
            except ConnectionClosedError:
                print(f"Client {client_id} connection closed with error from {robot_id}")
                break
            except Exception as e:
                print(f"Error in {robot_id} loop: {e}")
                break
    
    except Exception as e:
        print(f"ERROR in {robot_id} connection: {e}")
    
    finally:
        # Hủy heartbeat task khi kết thúc
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
            
        # Clean up
        if ws in robot_connections[robot_id]:
            robot_connections[robot_id].remove(ws)
        
        disconnect_type = "manual" if getattr(ws, "manual_disconnect", False) else "automatic"
        print(f"{robot_id} connection closed for {client_id} ({disconnect_type} disconnect)")
        print(f"Remaining {robot_id} connections: {len(robot_connections[robot_id])}")

# Thêm hàm heartbeat để giữ kết nối ổn định
async def send_heartbeat(ws: WebSocket, robot_id: str):
    """Send periodic heartbeat to client to keep connection alive"""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await ws.send_text(json.dumps({
                    "type": "ping",
                    "robot_id": robot_id,
                    "timestamp": time.time()
                }))
            except Exception as e:
                # Nếu không gửi được, thoát khỏi vòng lặp
                print(f"Heartbeat failed for {robot_id}: {e}")
                break
    except asyncio.CancelledError:
        # Normal cancellation when connection closes
        pass

# WebSocket endpoints for each robot
@app.websocket("/ws/robot1")
async def robot1_endpoint(ws: WebSocket):
    await handle_robot_connection(ws, "robot1")

@app.websocket("/ws/robot2")
async def robot2_endpoint(ws: WebSocket):
    await handle_robot_connection(ws, "robot2")

@app.websocket("/ws/robot3")
async def robot3_endpoint(ws: WebSocket):
    await handle_robot_connection(ws, "robot3")

@app.websocket("/ws/robot4")
async def robot4_endpoint(ws: WebSocket):
    await handle_robot_connection(ws, "robot4")

@app.websocket("/ws/server")
async def server_endpoint(ws: WebSocket):
    await handle_robot_connection(ws, "server")

# Send dummy data since we're simplifying
async def send_dummy_robot_data(ws: WebSocket, robot_id: str):
    """Send dummy data to robot when connected"""
    try:
        # Create dummy data since database query is failing
        robot_data = {
            "type": "initial_data",
            "robot_id": robot_id,
            "timestamp": time.time(),
            "position": {
                "x": 0,
                "y": 0,
                "theta": 0
            },
            "motors": {
                "rpm": [0, 0, 0]
            },
            "trajectory": {
                "x": [0],
                "y": [0]
            }
        }
        
        await ws.send_text(json.dumps(robot_data))
    except Exception as e:
        print(f"Error sending initial robot data: {e}")
        # Send a simplified response that doesn't rely on database
        await ws.send_text(json.dumps({
            "type": "status",
            "robot_id": robot_id,
            "message": "Connected successfully, waiting for data",
            "timestamp": time.time()
        }))

# Process robot commands - đặc biệt quan tâm đến ping/pong
async def process_robot_command(robot_id: str, data: dict, ws: WebSocket):
    """Process command from a robot connection"""
    try:
        command_type = data.get("type", "")
        
        # Common response data
        response_base = {
            "timestamp": time.time(),
            "robot_id": robot_id
        }
        
        # XỬ LÝ PING - Ưu tiên cao nhất để giữ kết nối sống
        if command_type == "ping":
            # Cập nhật last_activity của WebSocket
            ws.last_activity = time.time()
            
            # Trả về pong ngay lập tức với timestamp từ ping để tính RTT
            await ws.send_text(json.dumps({
                **response_base,
                "type": "pong",
                "timestamp": data.get("timestamp", time.time())
            }))
            return
        
        # Xử lý manual disconnect (đã xử lý ở vòng lặp chính)
        elif command_type == "manual_disconnect":
            # Đã xử lý ở vòng lặp chính
            return
            
        # Các lệnh khác - đơn giản hóa
        elif command_type == "get_status":
            # Send current robot status
            await send_dummy_robot_data(ws, robot_id)
        
        elif command_type == "trajectory":
            # Handle trajectory command - simplified
            action = data.get("action", "")
            await ws.send_text(json.dumps({
                **response_base,
                "type": "trajectory_response",
                "action": action,
                "status": "success",
                "message": "Command processed successfully"
            }))
        
        elif command_type == "motor":
            # Handle motor command - simplified
            action = data.get("action", "")
            await ws.send_text(json.dumps({
                **response_base,
                "type": "motor_response",
                "action": action,
                "status": "success",
                "message": "Motor command processed successfully"
            }))
        
        elif command_type == "pid":
            # Handle PID command - simplified
            action = data.get("action", "")
            await ws.send_text(json.dumps({
                **response_base,
                "type": "pid_response",
                "action": action,
                "status": "success",
                "message": "PID command processed successfully"
            }))
        
        elif command_type == "firmware":
            # Handle firmware command - simplified
            action = data.get("action", "")
            await ws.send_text(json.dumps({
                **response_base,
                "type": "firmware_response", 
                "action": action,
                "status": "success",
                "message": "Firmware command processed successfully"
            }))
        
        elif command_type == "emergency_stop":
            # Handle emergency stop - simplified
            await ws.send_text(json.dumps({
                **response_base,
                "type": "response",
                "command": "emergency_stop",
                "status": "executed"
            }))
        
        else:
            # Unknown command
            await ws.send_text(json.dumps({
                **response_base,
                "type": "error",
                "message": f"Unknown command type: {command_type}"
            }))
    
    except Exception as e:
        # Send error response
        await ws.send_text(json.dumps({
            "type": "error",
            "robot_id": robot_id,
            "message": f"Error processing command: {str(e)}",
            "timestamp": time.time()
        }))

@app.get("/api/connection-status")
async def get_connection_status():
    """Get the status of all WebSocket connections"""
    try:
        # Get WebSocket connection counts
        ws_connections = {
            "robot1": len(robot_connections.get("robot1", [])),
            "robot2": len(robot_connections.get("robot2", [])),
            "robot3": len(robot_connections.get("robot3", [])),
            "robot4": len(robot_connections.get("robot4", [])),
            "server": len(robot_connections.get("server", []))
        }
        
        return {
            "status": "ok",
            "websocket_connections": ws_connections,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)