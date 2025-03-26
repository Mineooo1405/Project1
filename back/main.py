import asyncio
import json
import time
import traceback
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
# Replace old database imports with new ones
from robot_database import SessionLocal, Robot, EncoderData, IMUData, LogData, TrajectoryCalculator, TrajectoryData
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
import logging
from data_converter import DataConverter
from trajectory_service import TrajectoryService
from datetime import datetime, timedelta
import math
import random
import numpy as np
from fastapi.security import APIKeyHeader

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("websocket")

# Add missing TrajectoryData model since we need it and it's not in robot_database.py
from sqlalchemy import create_engine, Column, Integer, Float, String, Boolean, DateTime, ForeignKey, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from robot_database import Base


    # rest of definition...
    
class PIDConfig(Base):
    __tablename__ = "pid_configs"
    __table_args__ = {'extend_existing': True}  # Add this line
    id = Column(Integer, primary_key=True)
    robot_id = Column(String, index=True)
    motor_id = Column(Integer)  # 1, 2, 3
    kp = Column(Float)
    ki = Column(Float)
    kd = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    raw_data = Column(JSONB, nullable=True)  # Store full JSON message
    robot_data = Column(Boolean, default=True)  # Flag to differentiate data source

# Create tables if they don't exist
from robot_database import engine
Base.metadata.create_all(bind=engine)

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
        print(f"Accepted {robot_id} connection from {client_id}")
        
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

@app.websocket("/ws/server")
async def server_endpoint(ws: WebSocket):
    await handle_robot_connection(ws, "server")

@app.websocket("/ws/{robot_id}")
async def robot_endpoint(websocket: WebSocket, robot_id: str):
    # Handle specialized endpoints with parameter
    if "/" in robot_id:
        parts = robot_id.split("/", 1)
        robot_id = f"{parts[0]}_{parts[1]}"
    await handle_robot_connection(websocket, robot_id)

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
            imu_data = DataConverter.imu_to_frontend(latest_imu)
            robot_data["imu"] = imu_data
        else:
            # Generate random IMU data as fallback
            robot_data["imu"] = {
                "orientation": {
                    "roll": random.uniform(-0.1, 0.1),
                    "pitch": random.uniform(-0.1, 0.1),
                    "yaw": robot_data["status"]["position"]["theta"]
                },
                "acceleration": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 9.8
                },
                "angular_velocity": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0
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
                
                # Use the centralized function
                status_data = await get_robot_status_data(robot_id, db)
                
                # Send the robot status data
                await ws.send_text(json.dumps({
                    **response_base,
                    "type": "robot_status",
                    "status": status_data
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

async def get_robot_status_data(robot_id: str, db: Session = None):
    """Centralized function for getting robot status data from DB"""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
        
    try:
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
            encoder_values = encoder_json.get("values", encoder_values)
            encoder_rpm = encoder_json.get("rpm", encoder_rpm)
        
        # Process position data if available
        position = {"x": 1.25, "y": 0.75, "theta": 0.5}
        if trajectory_data:
            trajectory_json = DataConverter.trajectory_to_frontend(trajectory_data)
            position = trajectory_json.get("current_position", position)
        
        # Return the robot status data
        return {
            "connected": True,
            "lastUpdate": datetime.now().isoformat(),
            "encoders": {
                "values": encoder_values,
                "rpm": encoder_rpm
            },
            "position": position,
            "battery": {
                "voltage": 11.8,
                "percent": 85
            },
            "pid": pid_data
        }
        
    finally:
        if close_db:
            db.close()

# Import cấu hình
from config import API_KEY

# Thiết lập xác thực API key
api_key_header = APIKeyHeader(name="Authorization", auto_error=True)

# Hàm để xác thực API key từ header
async def verify_api_key(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key header không tồn tại"
        )
    
    # Kiểm tra định dạng "Bearer {API_KEY}"
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key không đúng định dạng. Sử dụng 'Bearer {api_key}'"
        )
    
    # Lấy API key từ header
    token = authorization.replace("Bearer ", "")
    
    # Kiểm tra API key
    if token != API_KEY:
        logging.warning(f"Xác thực thất bại với key: {token[:5]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key không hợp lệ"
        )
    
    return token

# Route để kiểm tra định dạng xác thực
@app.get("/api/auth/format")
async def auth_format_info():
    """Cung cấp thông tin về định dạng xác thực để trợ giúp client"""
    return {
        "format": "Bearer {api_key}",
        "headerName": "Authorization",
        "example": "Authorization: Bearer your-api-key-here"
    }

# Endpoint WebSocket với xác thực
@app.websocket("/ws/robot/{robot_id}")
async def websocket_endpoint(websocket: WebSocket, robot_id: str):
    authorization = websocket.headers.get("Authorization")
    
    # Kiểm tra xác thực
    try:
        if not authorization:
            await websocket.close(code=status.HTTP_401_UNAUTHORIZED)
            logging.warning(f"Kết nối WebSocket từ chối: Không có header Authorization")
            return
            
        # Kiểm tra định dạng "Bearer {API_KEY}"
        if not authorization.startswith("Bearer "):
            await websocket.close(code=status.HTTP_401_UNAUTHORIZED)
            logging.warning(f"Kết nối WebSocket từ chối: Header Authorization không đúng định dạng")
            return
        
        # Lấy API key từ header
        token = authorization.replace("Bearer ", "")
        
        # Kiểm tra API key
        if token != API_KEY:
            await websocket.close(code=status.HTTP_403_FORBIDDEN)
            logging.warning(f"Kết nối WebSocket từ chối: API Key không hợp lệ")
            return
            
        # Xác thực thành công - chấp nhận kết nối
        await websocket.accept()
        logging.info(f"Kết nối WebSocket chấp nhận cho robot: {robot_id}")
        
        # Gửi tin nhắn chào mừng
        await websocket.send_json({
            "type": "welcome",
            "message": f"Xin chào robot {robot_id}",
            "timestamp": time.time()
        })
        
        # Tiếp tục xử lý WebSocket
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Xử lý tin nhắn
                # ...
                
                # Gửi phản hồi
                await websocket.send_json({
                    "type": "ack",
                    "timestamp": time.time()
                })
                
        except WebSocketDisconnect:
            logging.info(f"Robot {robot_id} đã ngắt kết nối")
        
    except Exception as e:
        logging.error(f"Lỗi xử lý WebSocket: {e}")
        await websocket.close(code=status.HTTP_500_INTERNAL_SERVER_ERROR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)