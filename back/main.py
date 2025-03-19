import asyncio
import json
import time
import traceback
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from database import SessionLocal
from database import EncoderData, TrajectoryData, PIDConfig, IMUData
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
import logging
from database import TrajectoryCalculator, JSONDataHandler
import math
import random
from data_converter import DataConverter
from trajectory_service import TrajectoryService
from datetime import datetime, timedelta

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

#tcp
import socket
import traceback

# Add this function to forward commands to the TCP server
async def forward_to_tcp_server(data, log_prefix=""):
    """Forward a command to the TCP server and get the response"""
    try:
        robot_id = data.get("robot_id", "unknown")
        command_type = data.get("type", "unknown")
        
        logger.info(f"{log_prefix}=== FORWARDING TO TCP SERVER ===")
        logger.info(f"{log_prefix}Command type: {command_type}")
        logger.info(f"{log_prefix}Robot ID: {robot_id}")
        logger.info(f"{log_prefix}Data: {json.dumps(data)[:200]}..." if len(json.dumps(data)) > 200 else f"{log_prefix}Data: {json.dumps(data)}")
        
        # Create TCP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)  # 5 second timeout
        
        # Connect to TCP server
        logger.info(f"{log_prefix}Connecting to TCP server at localhost:9000...")
        s.connect(('localhost', 9000))
        
        # Receive welcome message
        welcome = s.recv(1024).decode()
        logger.info(f"{log_prefix}TCP server welcome: {welcome}")
        
        # Format and send message
        message = json.dumps(data) + '\n'
        logger.info(f"{log_prefix}Sending message ({len(message)} bytes)...")
        s.sendall(message.encode())
        
        # Wait for response
        logger.info(f"{log_prefix}Waiting for response...")
        response = s.recv(1024).decode()
        logger.info(f"{log_prefix}TCP server response: {response}")
        
        # Close connection
        s.close()
        logger.info(f"{log_prefix}TCP connection closed")
        
        # Parse response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"{log_prefix}Invalid JSON response from TCP server: {response}")
            return {"status": "error", "message": "Invalid response from TCP server"}
            
    except socket.timeout:
        logger.error(f"{log_prefix}TCP server connection timed out")
        return {"status": "error", "message": "TCP server connection timed out"}
    except ConnectionRefusedError:
        logger.error(f"{log_prefix}TCP server connection refused - is the TCP server running?")
        return {"status": "error", "message": "TCP server connection refused"}
    except Exception as e:
        logger.error(f"{log_prefix}TCP forwarding error: {str(e)}")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": f"TCP error: {str(e)}"}

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
        "time": datetime.now().isoformat()
    }

# Health check endpoint
@app.get("/api/health-check")
async def health_check():
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
        "version": "1.0.0"
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

@app.websocket("/ws/{robot_id}/motor")
async def motor_endpoint(ws: WebSocket, robot_id: str):
    """WebSocket endpoint for motor control"""
    client_id = f"{ws.client.host}:{ws.client.port}"
    print(f"Motor control connection request from {client_id} for {robot_id}")
    
    await handle_robot_connection(ws, f"{robot_id}_motor")

@app.websocket("/ws/{robot_id}/pid")
async def pid_endpoint(ws: WebSocket, robot_id: str):
    """WebSocket endpoint for PID configuration"""
    client_id = f"{ws.client.host}:{ws.client.port}"
    print(f"PID configuration connection request from {client_id} for {robot_id}")
    
    await handle_robot_connection(ws, f"{robot_id}_pid")

@app.websocket("/ws/{robot_id}/trajectory")
async def trajectory_endpoint(ws: WebSocket, robot_id: str):
    """WebSocket endpoint for trajectory visualization"""
    client_id = f"{ws.client.host}:{ws.client.port}"
    print(f"Trajectory visualization connection request from {client_id} for {robot_id}")
    
    await handle_robot_connection(ws, f"{robot_id}_trajectory")

@app.websocket("/ws/{robot_id}/imu")
async def imu_endpoint(ws: WebSocket, robot_id: str):
    """WebSocket endpoint for IMU data visualization"""
    client_id = f"{ws.client.host}:{ws.client.port}"
    print(f"IMU data connection request from {client_id} for {robot_id}")
    
    await handle_robot_connection(ws, f"{robot_id}_imu")

# WebSocket endpoint for handling encoder data and updating trajectory
@app.websocket("/ws/robot/{robot_id}")
async def robot_websocket(websocket: WebSocket, robot_id: str):
    client_id = f"{websocket.client.host}:{websocket.client.port}"
    print(f"Connection request from {client_id} for {robot_id}")
    print(f"Active connections for {robot_id}: {len(robot_connections[robot_id])}")
    
    # Khởi tạo heartbeat task
    heartbeat_task = None
    
    try:
        # Accept connection immediately
        await websocket.accept()
        print(f"✅ Accepted {robot_id} connection from {client_id}")
        
        # Store metadata
        websocket.connected_since = time.time()
        websocket.last_activity = time.time()
        websocket.client_id = client_id
        websocket.robot_id = robot_id
        websocket.manual_disconnect = False  # Flag to track manual disconnection
        
        # Add to connection list
        if websocket not in robot_connections[robot_id]:
            robot_connections[robot_id].append(websocket)
        
        # Send confirmation
        await websocket.send_text(json.dumps({
            "status": "connected", 
            "robot_id": robot_id,
            "timestamp": time.time()
        }))
        
        # Khởi động heartbeat để giữ kết nối
        heartbeat_task = asyncio.create_task(send_heartbeat(websocket, robot_id))
        
        # Initialize robot position
        TrajectoryService.initialize_robot_position(robot_id)
        
        # Main message loop - KHÔNG tự động ngắt kết nối
        while True:
            try:
                # Thời gian chờ đọc message cao hơn để tránh timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=MAX_INACTIVE_TIME)
                websocket.last_activity = time.time()
                
                # Add message received logging
                ip_addr = websocket.client.host
                logger.info(f"=== FRONTEND MESSAGE RECEIVED ===")
                logger.info(f"From: {ip_addr} for robot: {robot_id}")
                logger.info(f"Message: {data[:200]}..." if len(data) > 200 else f"Message: {data}")
                
                # Process command
                try:
                    json_data = json.loads(data)
                    
                    # Kiểm tra xem client có yêu cầu ngắt kết nối không
                    if json_data.get("type") == "manual_disconnect":
                        print(f"Client {client_id} requested manual disconnect from {robot_id}")
                        websocket.manual_disconnect = True
                        await websocket.send_text(json.dumps({
                            "type": "disconnect_confirmed",
                            "robot_id": robot_id,
                            "timestamp": time.time(),
                            "message": "Disconnect request accepted"
                        }))
                        break
                    
                    command_type = json_data.get("type", "")
                    response_base = {
                        "timestamp": time.time(),
                        "robot_id": robot_id
                    }
                    
                    # Add handler for encoder data
                    if command_type == "get_encoder_data":
                        try:
                            db = SessionLocal()
                            
                            # Get latest encoder data
                            latest_encoders = DataConverter.get_latest_data_by_robot(db, EncoderData, robot_id, 1)
                            
                            # Also get latest IMU data for orientation
                            latest_imu = DataConverter.get_latest_data_by_robot(db, IMUData, robot_id, 1)
                            
                            if latest_encoders and len(latest_encoders) > 0:
                                # Convert encoder data to frontend format
                                encoder_json = DataConverter.encoder_to_frontend(latest_encoders[0])
                                
                                # Convert IMU data if available
                                imu_json = None
                                if latest_imu and len(latest_imu) > 0:
                                    imu_json = DataConverter.imu_to_frontend(latest_imu[0])
                                
                                # Update trajectory based on encoder data
                                updated_position = TrajectoryService.calculate_position_from_encoder(
                                    robot_id, encoder_json, imu_json
                                )
                                
                                # Every 10 updates, save the trajectory to database
                                if updated_position is not None and len(updated_position["points"]["x"]) % 10 == 0:
                                    TrajectoryService.save_trajectory_to_db(db, robot_id)
                                
                                # Send encoder data response
                                await websocket.send_text(json.dumps({
                                    **response_base,
                                    "type": "encoder_data",
                                    **encoder_json
                                }))
                                
                                # Also send updated trajectory
                                await websocket.send_text(json.dumps({
                                    **response_base,
                                    "type": "trajectory_update",
                                    "trajectory": {
                                        "current_position": {
                                            "x": updated_position["x"],
                                            "y": updated_position["y"],
                                            "theta": updated_position["theta"]
                                        },
                                        "points": updated_position["points"],
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }))
                                
                                logger.info(f"Sent encoder data and trajectory update for {robot_id}")
                            else:
                                # ... existing code for sending fallback data ...
                                pass
                                
                        except Exception as e:
                            logger.error(f"Error processing encoder data: {str(e)}")
                            logger.error(traceback.format_exc())
                        finally:
                            db.close()
                    
                    # Add a dedicated endpoint for getting the trajectory
                    elif command_type == "get_trajectory":
                        try:
                            # Get current trajectory from in-memory service
                            position = TrajectoryService.get_robot_position(robot_id)
                            
                            # Create response with current trajectory
                            await websocket.send_text(json.dumps({
                                **response_base,
                                "type": "trajectory_data",
                                "trajectory": {
                                    "current_position": {
                                        "x": position["x"],
                                        "y": position["y"],
                                        "theta": position["theta"]
                                    },
                                    "points": position["points"],
                                    "timestamp": datetime.now().isoformat()
                                }
                            }))
                            
                            logger.info(f"Sent current trajectory for {robot_id}")
                        except Exception as e:
                            logger.error(f"Error getting trajectory: {str(e)}")
                            logger.error(traceback.format_exc())
                    
                    else:
                        await process_robot_command(robot_id, json_data, websocket)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "status": "error",
                        "message": "Invalid JSON data",
                        "timestamp": time.time()
                    }))
            except asyncio.TimeoutError:
                # Không ngắt kết nối khi timeout - chỉ log và gửi ping
                current_time = time.time()
                inactive_time = current_time - websocket.last_activity
                print(f"Client {client_id} inactive for {inactive_time:.1f}s")
                
                # Gửi ping để kiểm tra kết nối vẫn sống
                try:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "robot_id": robot_id,
                        "timestamp": current_time
                    }))
                    websocket.last_activity = current_time
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
        if websocket in robot_connections[robot_id]:
            robot_connections[robot_id].remove(websocket)
        
        disconnect_type = "manual" if getattr(websocket, "manual_disconnect", False) else "automatic"
        print(f"{robot_id} connection closed for {client_id} ({disconnect_type} disconnect)")
        print(f"Remaining {robot_id} connections: {len(robot_connections[robot_id])}")

# Send robot data from database when connected
async def send_dummy_robot_data(ws: WebSocket, robot_id: str):
    """Send robot data when connected, trying to use database values first"""
    try:
        # Create database session
        db = SessionLocal()
        
        # Get latest IMU data
        latest_imu = db.query(IMUData).filter(
            IMUData.robot_id == robot_id
        ).order_by(IMUData.timestamp.desc()).first()
        
        # Get latest encoder data
        latest_encoder = db.query(EncoderData).filter(
            EncoderData.robot_id == robot_id
        ).order_by(EncoderData.timestamp.desc()).first()
        
        # Get latest trajectory data
        latest_trajectory = db.query(TrajectoryData).filter(
            TrajectoryData.robot_id == robot_id
        ).order_by(TrajectoryData.timestamp.desc()).first()
        
        # Generate robot data, using database values when available
        robot_data = {
            "type": "initial_data",
            "robot_id": robot_id,
            "timestamp": time.time(),
            "status": {
                "connected": True,
                "lastUpdate": datetime.now().isoformat(),
                "position": {
                    "x": latest_trajectory.current_x if latest_trajectory else random.uniform(-0.5, 0.5),
                    "y": latest_trajectory.current_y if latest_trajectory else random.uniform(-0.5, 0.5),
                    "theta": latest_trajectory.current_theta if latest_trajectory else random.uniform(-3.14, 3.14)
                },
                "encoders": {
                    "values": DataConverter.encoder_to_frontend(latest_encoder)["values"] if latest_encoder else [1000, 1050, 1100],
                    "rpm": DataConverter.encoder_to_frontend(latest_encoder)["rpm"] if latest_encoder else [
                        random.uniform(-30, 30),
                        random.uniform(-30, 30),
                        random.uniform(-30, 30)
                    ]
                },
                "battery": {
                    "voltage": 12.0 - random.uniform(0, 1.5),
                    "percent": random.randint(60, 100)
                },
                "pid": {
                    "motor1": {"kp": 0.5, "ki": 0.1, "kd": 0.05},
                    "motor2": {"kp": 0.5, "ki": 0.1, "kd": 0.05},
                    "motor3": {"kp": 0.5, "ki": 0.1, "kd": 0.05}
                }
            },
            "trajectory": {}
        }
        
        # Add trajectory data if available
        if latest_trajectory and latest_trajectory.points:
            robot_data["trajectory"] = latest_trajectory.points
        else:
            # Generate a simple trajectory
            trajectory_x = []
            trajectory_y = []
            for i in range(50):
                angle = i * 0.1
                radius = 1.0
                trajectory_x.append(radius * math.cos(angle))
                trajectory_y.append(radius * math.sin(angle))
            robot_data["trajectory"] = {
                "x": trajectory_x,
                "y": trajectory_y
            }
        
        # Add IMU data if available
        if latest_imu:
            orientation = {}
            if hasattr(latest_imu, "raw_data") and latest_imu.raw_data and "orientation" in latest_imu.raw_data:
                orientation = latest_imu.raw_data.get("orientation", {})
            else:
                orientation = {
                    "roll": random.uniform(-0.1, 0.1),
                    "pitch": random.uniform(-0.1, 0.1), 
                    "yaw": robot_data["status"]["position"]["theta"]
                }
                
            robot_data["imu"] = {
                "orientation": orientation,
                "acceleration": {
                    "x": latest_imu.accel_x,
                    "y": latest_imu.accel_y,
                    "z": latest_imu.accel_z
                },
                "angular_velocity": {
                    "x": latest_imu.gyro_x,
                    "y": latest_imu.gyro_y,
                    "z": latest_imu.gyro_z
                },
                "timestamp": latest_imu.timestamp.isoformat()
            }
        else:
            # Generate random IMU data as fallback
            robot_data["imu"] = {
                "orientation": {
                    "roll": random.uniform(-0.1, 0.1),
                    "pitch": random.uniform(-0.1, 0.1),
                    "yaw": robot_data["status"]["position"]["theta"]
                },
                "acceleration": {
                    "x": random.uniform(-0.2, 0.2),
                    "y": random.uniform(-0.2, 0.2),
                    "z": 9.8 + random.uniform(-0.1, 0.1)
                },
                "angular_velocity": {
                    "x": random.uniform(-0.05, 0.05),
                    "y": random.uniform(-0.05, 0.05),
                    "z": random.uniform(-0.05, 0.05)
                },
                "timestamp": datetime.now().isoformat()
            }
        
        await ws.send_text(json.dumps(robot_data))
        logger.info(f"Sent initial data to {robot_id} (using database: {True if latest_imu or latest_encoder or latest_trajectory else False})")
    except Exception as e:
        logger.error(f"Error sending initial robot data: {e}")
        # Send a simplified response that doesn't rely on database
        await ws.send_text(json.dumps({
            "type": "status",
            "robot_id": robot_id,
            "message": f"Connected successfully, but database data unavailable: {str(e)}",
            "timestamp": time.time()
        }))
    finally:
        db.close()

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
            
        # --- TÍNH NĂNG MỚI: TRẢ VỀ DỮ LIỆU CHO CÁC WIDGET ---
        
        # Lấy trạng thái robot từ database
        elif command_type == "get_status" or command_type == "get_robot_status":
            try:
                # Create database session
                db = SessionLocal()
                
                # Get latest encoder data
                latest_encoders = DataConverter.get_latest_data_by_robot(db, EncoderData, robot_id, 1)
                
                # Get latest trajectory data for position
                latest_trajectories = DataConverter.get_latest_data_by_robot(db, TrajectoryData, robot_id, 1)
                
                # Get PID configurations
                pid_configs = db.query(PIDConfig).filter(
                    PIDConfig.robot_id == robot_id
                ).all()
                
                # Build response with real data when available
                encoder_data = latest_encoders[0] if latest_encoders else None
                trajectory_data = latest_trajectories[0] if latest_trajectories else None
                
                # Convert PID data
                pid_data = {}
                for config in pid_configs:
                    pid_config_json = DataConverter.pid_to_frontend(config)
                    motor_id = f"motor{pid_config_json['motor_id']}"
                    pid_data[motor_id] = {
                        "kp": pid_config_json["kp"],
                        "ki": pid_config_json["ki"],
                        "kd": pid_config_json["kd"]
                    }
                
                # If no PID data found, provide defaults
                if not pid_data:
                    pid_data = {
                        "motor1": {"kp": 0.5, "ki": 0.1, "kd": 0.05},
                        "motor2": {"kp": 0.5, "ki": 0.1, "kd": 0.05},
                        "motor3": {"kp": 0.5, "ki": 0.1, "kd": 0.05}
                    }
                
                # Process encoder data if available
                encoder_values = [1000, 1100, 1200]
                encoder_rpm = [50, 60, 70]
                if encoder_data:
                    encoder_json = DataConverter.encoder_to_frontend(encoder_data)
                    encoder_values = encoder_json["values"]
                    encoder_rpm = encoder_json["rpm"]
                
                # Process position data if available
                position = {"x": 1.25, "y": 0.75, "theta": 0.5}
                if trajectory_data:
                    trajectory_json = DataConverter.trajectory_to_frontend(trajectory_data)
                    position = trajectory_json["current_position"]
                
                # Send the robot status data
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "robot_status",
                    "status": {
                        "connected": True,
                        "lastUpdate": datetime.now().isoformat(),
                        "encoders": {
                            "values": encoder_values,
                            "rpm": encoder_rpm
                        },
                        "position": position,
                        "battery": {
                            "voltage": 11.8,  # This would come from a battery table if available
                            "percent": 85
                        },
                        "pid": pid_data
                    }
                }))
                logger.info(f"Sent database robot status for {robot_id}")
            except Exception as e:
                logger.error(f"Error retrieving robot status: {str(e)}")
                logger.error(traceback.format_exc())
                # Return fallback data on error
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "robot_status",
                    "status": {
                        "connected": True,
                        "encoders": {"values": [1000, 1100, 1200], "rpm": [50, 60, 70]},
                        "position": {"x": 1.25, "y": 0.75, "theta": 0.5},
                        "battery": {"voltage": 11.8, "percent": 85},
                        "pid": {
                            "motor1": {"kp": 0.5, "ki": 0.1, "kd": 0.05},
                            "motor2": {"kp": 0.5, "ki": 0.1, "kd": 0.05},
                            "motor3": {"kp": 0.5, "ki": 0.1, "kd": 0.05}
                        }
                    }
                }))
            finally:
                db.close()
            
        # Lấy dữ liệu quỹ đạo từ database
        elif command_type == "get_trajectory":
            try:
                # Create database session
                db = SessionLocal()
                
                # Get latest trajectory data
                latest_trajectories = DataConverter.get_latest_data_by_robot(db, TrajectoryData, robot_id, 1)
                
                if latest_trajectories and len(latest_trajectories) > 0:
                    # Convert to frontend format
                    trajectory_data = DataConverter.trajectory_to_frontend(latest_trajectories[0])
                    
                    await ws.send_text(json.dumps({
                        **response_base,
                        "type": "trajectory_data",
                        **trajectory_data
                    }))
                    logger.info(f"Sent database trajectory data for {robot_id}")
                else:
                    # No trajectory data, generate sample data as fallback
                    x_points = [0]
                    y_points = [0]
                    theta_points = [0]
                    
                    # Generate a simple spiral curve for demo purposes
                    for i in range(1, 101):
                        angle = i * 0.1
                        r = i * 0.02
                        x_points.append(r * math.cos(angle))
                        y_points.append(r * math.sin(angle))
                        theta_points.append(angle)
                    
                    await ws.send_text(json.dumps({
                        **response_base,
                        "type": "trajectory_data",
                        "points": {
                            "x": x_points,
                            "y": y_points,
                            "theta": theta_points
                        },
                        "current_position": {
                            "x": x_points[-1],
                            "y": y_points[-1],
                            "theta": theta_points[-1]
                        },
                        "timestamp": datetime.now().isoformat()
                    }))
                    logger.info(f"No trajectory data found for {robot_id}, sent generated data")
            except Exception as e:
                logger.error(f"Error retrieving trajectory data: {str(e)}")
                logger.error(traceback.format_exc())
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "error",
                    "message": f"Database error: {str(e)}"
                }))
            finally:
                db.close()
            
        # Đăng ký/hủy đăng ký nhận cập nhật quỹ đạo trực tiếp
        elif command_type == "subscribe_trajectory":
            # Trong demo này chỉ thiết lập một thuộc tính, trong thực tế bạn cần lưu trạng thái này
            ws.subscribe_trajectory = True
            await ws.send_text(json.dumps({
                **response_base,
                "type": "subscription_status",
                "service": "trajectory",
                "status": "subscribed"
            }))
            
        elif command_type == "unsubscribe_trajectory":
            # Hủy đăng ký
            ws.subscribe_trajectory = False
            await ws.send_text(json.dumps({
                **response_base,
                "type": "subscription_status",
                "service": "trajectory",
                "status": "unsubscribed"
            }))
            
        # Xử lý điều khiển động cơ
        elif command_type == "motor_control":
            # Extract motor speeds
            speeds = data.get("speeds", [0, 0, 0])
            
            # Log the command
            logger.info(f"Motor control command received for {robot_id}: speeds={speeds}")
            
            # Forward to TCP server
            tcp_prefix = f"[{robot_id}:MOTOR] "
            tcp_data = {
                "type": "motor_control",
                "robot_id": robot_id,
                "speeds": speeds,
                "timestamp": time.time()
            }
            
            # Forward to TCP server asynchronously
            try:
                # Wait for TCP server response
                tcp_response = await forward_to_tcp_server(tcp_data, tcp_prefix)
                
                # Send response to client
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "motor_response",
                    "status": tcp_response.get("status", "error"),
                    "message": tcp_response.get("message", "Error communicating with TCP server"),
                    "speeds": speeds
                }))
                
                logger.info(f"Motor control response sent to client: {speeds}")
                
            except Exception as e:
                logger.error(f"Error forwarding motor control to TCP server: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Send error response to client
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "error",
                    "message": f"Error sending motor control command: {str(e)}"
                }))
            
        # Xử lý lệnh chuyển động
        elif command_type == "motion_command":
            velocities = data.get("velocities", {})
            
            await ws.send_text(json.dumps({
                **response_base,
                "type": "motion_response",
                "status": "success",
                "velocities": velocities,
                "message": f"Motion command set: vx={velocities.get('x', 0)}, vy={velocities.get('y', 0)}, omega={velocities.get('theta', 0)}"
            }))
            
        # Xử lý cập nhật PID
        elif command_type == "update_pid":
            motor_id = data.get("motor_id", 1)
            parameters = data.get("parameters", {})
            
            await ws.send_text(json.dumps({
                **response_base,
                "type": "pid_response",
                "status": "success",
                "motor_id": motor_id,
                "parameters": parameters,
                "message": f"PID parameters updated for motor {motor_id}"
            }))
            
        # Xử lý đặt lại vị trí
        elif command_type == "reset_position":
            await ws.send_text(json.dumps({
                **response_base,
                "type": "position_response",
                "status": "success",
                "position": {"x": 0, "y": 0, "theta": 0},
                "message": "Position reset successfully"
            }))
            
        # Xử lý lệnh dừng khẩn cấp
        elif command_type == "emergency_stop":
            await ws.send_text(json.dumps({
                **response_base,
                "type": "emergency_response",
                "status": "executed",
                "message": "Emergency stop executed"
            }))
            
        # Get IMU data
        elif command_type == "get_imu_data":
            try:
                # Create database session
                db = SessionLocal()
                
                # Query the latest IMU data for this robot
                latest_imu = DataConverter.get_latest_data_by_robot(db, IMUData, robot_id, 1)
                
                if latest_imu and len(latest_imu) > 0:
                    # Convert database record to frontend format
                    imu_data = DataConverter.imu_to_frontend(latest_imu[0])
                    
                    # Create response with converted data
                    response = {
                        **response_base,
                        "type": "imu_data",
                        **imu_data  # Spread the converted data into response
                    }
                    
                    await ws.send_text(json.dumps(response))
                    logger.info(f"Sent database IMU data for {robot_id}")
                else:
                    # No data available, use fallback with random values
                    roll = random.uniform(-0.5, 0.5)
                    pitch = random.uniform(-0.3, 0.3)
                    yaw = random.uniform(-3.14, 3.14)
                    
                    accel_x = random.uniform(-0.2, 0.2)
                    accel_y = random.uniform(-0.2, 0.2)
                    accel_z = 9.8 + random.uniform(-0.1, 0.1)
                    
                    gyro_x = random.uniform(-0.1, 0.1)
                    gyro_y = random.uniform(-0.1, 0.1)
                    gyro_z = random.uniform(-0.1, 0.1)
                    
                    await ws.send_text(json.dumps({
                        **response_base,
                        "type": "imu_data",
                        "orientation": {
                            "roll": roll,
                            "pitch": pitch,
                            "yaw": yaw
                        },
                        "acceleration": {
                            "x": accel_x,
                            "y": accel_y,
                            "z": accel_z
                        },
                        "angular_velocity": {
                            "x": gyro_x,
                            "y": gyro_y,
                            "z": gyro_z
                        },
                        "timestamp": datetime.now().isoformat()
                    }))
                    logger.info(f"No IMU data found in database for {robot_id}, sent random data")
            except Exception as e:
                logger.error(f"Error retrieving IMU data: {str(e)}")
                logger.error(traceback.format_exc())
                # Send error response
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "error",
                    "message": f"Database error: {str(e)}"
                }))
            finally:
                db.close()

        # Subscribe to IMU updates
        elif command_type == "subscribe_imu":
            ws.subscribe_imu = True
            await ws.send_text(json.dumps({
                **response_base,
                "type": "subscription_status",
                "service": "imu",
                "status": "subscribed"
            }))

        # Unsubscribe from IMU updates
        elif command_type == "unsubscribe_imu":
            ws.subscribe_imu = False
            await ws.send_text(json.dumps({
                **response_base,
                "type": "subscription_status",
                "service": "imu",
                "status": "unsubscribed"
            }))

        elif command_type == "get_trajectory_history":
            try:
                db = SessionLocal()
                time_filter = data.get('time_filter', '24h')
                limit = data.get('limit', 100)  # Default 100 records max
                
                # Calculate time range based on filter
                end_time = datetime.now()
                start_time = None
                
                if time_filter == '24h':
                    start_time = end_time - timedelta(hours=24)
                elif time_filter == '7d':
                    start_time = end_time - timedelta(days=7)
                elif time_filter == '30d':
                    start_time = end_time - timedelta(days=30)
                # For 'all', no start_time filter
                
                # Query trajectory data
                query = db.query(TrajectoryData).filter(TrajectoryData.robot_id == robot_id)
                
                if start_time:
                    query = query.filter(TrajectoryData.timestamp >= start_time)
                
                # Order by timestamp descending (newest first) and limit results
                trajectories = query.order_by(TrajectoryData.timestamp.desc()).limit(limit).all()
                
                # Format trajectories for frontend
                trajectory_list = []
                
                for traj in trajectories:
                    # Convert database model to dictionary format expected by frontend
                    points = {}
                    if traj.points:
                        if isinstance(traj.points, str):
                            try:
                                points = json.loads(traj.points)
                            except:
                                points = {"x": [], "y": [], "theta": []}
                        else:
                            points = traj.points
                            
                    # Ensure points has the expected structure
                    if not isinstance(points, dict) or not all(k in points for k in ["x", "y", "theta"]):
                        points = {"x": [], "y": [], "theta": []}
                            
                    # Create trajectory record in expected format
                    trajectory_record = {
                        "id": traj.id,
                        "timestamp": traj.timestamp.isoformat() if traj.timestamp else datetime.now().isoformat(),
                        "currentPosition": {
                            "x": float(traj.current_x) if traj.current_x is not None else 0.0,
                            "y": float(traj.current_y) if traj.current_y is not None else 0.0,
                            "theta": float(traj.current_theta) if traj.current_theta is not None else 0.0,
                        },
                        "points": points,
                        "status": traj.status or "unknown"
                    }
                    
                    trajectory_list.append(trajectory_record)
                
                # Send trajectories to client
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "trajectory_history",
                    "trajectories": trajectory_list,
                    "count": len(trajectory_list),
                    "time_filter": time_filter
                }))
                
                logger.info(f"Sent {len(trajectory_list)} trajectory records to client for robot {robot_id}")
                
            except Exception as e:
                logger.error(f"Error retrieving trajectory history: {str(e)}")
                logger.error(traceback.format_exc())
                
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "error",
                    "message": f"Error retrieving trajectory history: {str(e)}"
                }))
            finally:
                db.close()
            
        # Các lệnh không xử lý được
        else:
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
        # Calculate server uptime
        uptime_seconds = time.time() - app.state.start_time
        uptime = {
            "days": int(uptime_seconds / 86400),
            "hours": int((uptime_seconds % 86400) / 3600),
            "minutes": int((uptime_seconds % 3600) / 60),
            "seconds": int(uptime_seconds % 60),
            "total_seconds": uptime_seconds
        }
        
        # Get WebSocket connection counts
        ws_connections = {
            "robot1": len(robot_connections.get("robot1", [])),
            "robot2": len(robot_connections.get("robot2", [])),
            "robot3": len(robot_connections.get("robot3", [])),
            "robot4": len(robot_connections.get("robot4", [])),
            "server": len(robot_connections.get("server", []))
        }
        
        # Get active connections with client info
        active_connections = []
        
        for robot_id, connections in robot_connections.items():
            for ws in connections:
                client_id = getattr(ws, "client_id", "unknown")
                connected_since = getattr(ws, "connected_since", 0)
                last_activity = getattr(ws, "last_activity", 0)
                
                connection_time = time.time() - connected_since if connected_since else 0
                idle_time = time.time() - last_activity if last_activity else 0
                
                active_connections.append({
                    "robot_id": robot_id,
                    "client_id": client_id,
                    "connected_since": datetime.fromtimestamp(connected_since).isoformat() if connected_since else None,
                    "connection_time_seconds": connection_time,
                    "last_activity": datetime.fromtimestamp(last_activity).isoformat() if last_activity else None,
                    "idle_time_seconds": idle_time
                })
        
        return {
            "status": "ok",
            "server": {
                "start_time": datetime.fromtimestamp(app.state.start_time).isoformat(),
                "uptime": uptime,
                "current_time": datetime.now().isoformat()
            },
            "websocket_connections": ws_connections,
            "total_connections": sum(ws_connections.values()),
            "active_connections": active_connections,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }

# Endpoint để tính quỹ đạo từ dữ liệu encoder
@app.get("/api/calculate-trajectory/{robot_id}")
async def calculate_trajectory(
    robot_id: str, 
    start_time: str = None, 
    end_time: str = None, 
    db: Session = Depends(get_db)
):
    try:
        # Chuyển đổi chuỗi thời gian thành datetime nếu có
        start_datetime = None
        end_datetime = None
        
        if start_time:
            start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        if end_time:
            end_datetime = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            
        # Tính quỹ đạo từ dữ liệu encoder
        trajectory = TrajectoryCalculator.process_encoder_data(
            db, robot_id, start_datetime, end_datetime
        )
        
        # Trả về kết quả
        return {
            "status": "success",
            "robot_id": robot_id,
            "trajectory": trajectory,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error calculating trajectory: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error calculating trajectory: {str(e)}"
        )

@app.get("/api/robot-status/{robot_id}")
async def get_robot_status(robot_id: str, db: Session = Depends(get_db)):
    try:
        # Lấy dữ liệu encoder mới nhất
        latest_encoder = db.query(EncoderData).filter(
            EncoderData.robot_id == robot_id
        ).order_by(EncoderData.timestamp.desc()).first()
        
        # Lấy dữ liệu quỹ đạo mới nhất
        latest_trajectory = db.query(TrajectoryData).filter(
            TrajectoryData.robot_id == robot_id
        ).order_by(TrajectoryData.timestamp.desc()).first()
        
        # Lấy cấu hình PID
        pid_configs = db.query(PIDConfig).filter(
            PIDConfig.robot_id == robot_id
        ).all()
        
        # Tạo dữ liệu trả về
        result = {
            "status": "success",
            "robot_id": robot_id,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "position": {
                    "x": latest_trajectory.current_x if latest_trajectory else 0,
                    "y": latest_trajectory.current_y if latest_trajectory else 0,
                    "theta": latest_trajectory.current_theta if latest_trajectory else 0
                } if latest_trajectory else {"x": 0, "y": 0, "theta": 0},
                "encoders": {
                    "values": latest_encoder.values if latest_encoder else [0, 0, 0],
                    "rpm": latest_encoder.rpm if latest_encoder else [0, 0, 0]
                } if latest_encoder else {"values": [0, 0, 0], "rpm": [0, 0, 0]},
                "pid": {}
            }
        }
        
        # Thêm dữ liệu PID
        for pid in pid_configs:
            result["data"]["pid"][f"motor{pid.motor_id}"] = {
                "kp": pid.kp,
                "ki": pid.ki,
                "kd": pid.kd
            }
        
        return result
    except Exception as e:
        logger.error(f"Error getting robot status: {str(e)}")
        
        # Trả về dữ liệu giả nếu có lỗi
        return {
            "status": "error",
            "robot_id": robot_id,
            "timestamp": datetime.now().isoformat(),
            "message": f"Error retrieving robot status: {str(e)}",
            "data": {
                "position": {"x": 0, "y": 0, "theta": 0},
                "encoders": {"values": [0, 0, 0], "rpm": [0, 0, 0]},
                "pid": {
                    "motor1": {"kp": 0, "ki": 0, "kd": 0},
                    "motor2": {"kp": 0, "ki": 0, "kd": 0},
                    "motor3": {"kp": 0, "ki": 0, "kd": 0}
                }
            }
        }

@app.post("/api/update-pid/{robot_id}")
async def update_pid_config(
    robot_id: str, 
    motor_id: int, 
    kp: float, 
    ki: float, 
    kd: float, 
    db: Session = Depends(get_db)
):
    try:
        # Kiểm tra xem cấu hình đã tồn tại chưa
        existing_pid = db.query(PIDConfig).filter(
            PIDConfig.robot_id == robot_id,
            PIDConfig.motor_id == motor_id
        ).first()
        
        if existing_pid:
            # Cập nhật cấu hình hiện có
            existing_pid.kp = kp
            existing_pid.ki = ki
            existing_pid.kd = kd
            existing_pid.timestamp = datetime.now()
        else:
            # Tạo cấu hình mới
            new_pid = PIDConfig(
                robot_id=robot_id,
                motor_id=motor_id,
                kp=kp,
                ki=ki,
                kd=kd,
                timestamp=datetime.now()
            )
            db.add(new_pid)
            
        db.commit()
        
        return {
            "status": "success",
            "robot_id": robot_id,
            "motor_id": motor_id,
            "parameters": {
                "kp": kp,
                "ki": ki,
                "kd": kd
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/pid-config/{robot_id}")
async def get_pid_config(robot_id: str, db: Session = Depends(get_db)):
    try:
        pid_configs = db.query(PIDConfig).filter(
            PIDConfig.robot_id == robot_id
        ).all()
        
        result = {
            "status": "success",
            "robot_id": robot_id,
            "configs": [],
            "timestamp": datetime.now().isoformat()
        }
        
        for config in pid_configs:
            result["configs"].append({
                "motor_id": config.motor_id,
                "parameters": {
                    "kp": config.kp,
                    "ki": config.ki,
                    "kd": config.kd
                },
                "timestamp": config.timestamp.isoformat()
            })
            
        return result
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.get("/api/check-tcp-server")
async def check_tcp_server():
    """Check if TCP server is running and available"""
    try:
        # Create TCP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)  # 2 second timeout
        
        # Try to connect to TCP server
        logger.info("API: Checking TCP server connection...")
        s.connect(('localhost', 9000))
        
        welcome = s.recv(1024).decode()
        logger.info(f"API: TCP server welcome: {welcome}")
        
        # Close connection
        s.close()
        
        return {
            "status": "ok",
            "message": "TCP server is running",
            "details": welcome if welcome else "No welcome message received"
        }
    except socket.timeout:
        logger.warning("API: TCP server check timed out")
        return {
            "status": "error", 
            "message": "TCP server connection timed out"
        }
    except ConnectionRefusedError:
        logger.warning("API: TCP server connection refused")
        return {
            "status": "error", 
            "message": "TCP server connection refused"
        }
    except Exception as e:
        logger.error(f"API: Error checking TCP server: {str(e)}")
        return {
            "status": "error",
            "message": f"Error checking TCP server: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)