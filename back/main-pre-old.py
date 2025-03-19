import asyncio
import threading
import datetime
import json
import socket
import time
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from TCPConnectionManager import TCPConnectionManager
from database import SessionLocal, FirmwareFile, FirmwareUpdate, MotorControl, MotionCommand, PIDConfig
from database import EncoderData, TrajectoryData, IMUData, EmergencyCommand, JSONDataHandler, CommandLog
import random
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("websocket")

# Database session + Global manager

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

wheel_radius = 0.03
robot_radius = 0.153

def compute_velocity(theta, omega):
    H = np.array([
        [-np.sin(theta),   np.cos(theta),           robot_radius],
        [-np.sin(np.pi/3 - theta), -np.cos(np.pi/3 - theta), robot_radius],
        [ np.sin(np.pi/3 + theta), -np.cos(np.pi/3 + theta), robot_radius]
    ])
    # RPM -> rad/s
    omega_rad = np.array(omega) * (2 * np.pi / 60)
    # rad/s -> m/s
    omega_scaled = omega_rad * wheel_radius
    try:
        velocities = np.linalg.solve(H, omega_scaled)
    except np.linalg.LinAlgError:
        print("[ERROR] Không thể giải hệ phương trình động học!")
        return 0, 0, 0
    print(f"[DEBUG] v_x: {velocities[0]:.4f} m/s, v_y: {velocities[1]:.4f} m/s")
    return velocities[0], velocities[1], 0

def update_position(robot_id, theta, omega, dt, db):
    if isinstance(omega, str):
        omega = json.loads(omega)
    omega = [float(w) for w in omega]
    
    # Sửa từ IMULog sang IMUData
    latest = db.query(IMUData).order_by(IMUData.timestamp.desc()).first()
    
    # Cập nhật tên thuộc tính phù hợp với IMUData
    x = latest.accel_x if latest else 0.0
    y = latest.accel_y if latest else 0.0
    
    print(f"[DEBUG] Old Position: x={x:.4f}, y={y:.4f}")
    v_x, v_y, _ = compute_velocity(theta, omega)
    x += v_x * dt
    y += v_y * dt
    print(f"[DEBUG] New Position: x={x:.4f}, y={y:.4f}")
    
    # Tạo đối tượng IMUData thay vì IMULog
    imu_entry = IMUData(
        yaw=theta,
        # Lưu omega dưới dạng JSON trong JSONB raw_data
        raw_data={"omega": omega},
        accel_x=x,
        accel_y=y,
        # Các giá trị khác cần thiết cho IMUData
        roll=0.0,
        pitch=0.0,
        accel_z=0.0,
        ang_vel_x=0.0,
        ang_vel_y=0.0,
        ang_vel_z=0.0,
        timestamp=datetime.datetime.now()
    )
    db.add(imu_entry)
    db.commit()
    asyncio.create_task(broadcast_trajectory())

# FastAPI + Lifespan

from fastapi import HTTPException

# Thay vì @app.on_event("startup"), ta chuyển logic broadcast_loop vào lifespan
# Khởi tạo TCP Manager và chạy nó trong một thread riêng
tcp_manager = TCPConnectionManager()
threading.Thread(target=tcp_manager.start, daemon=True).start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi động broadcast loop để gửi dữ liệu tới WebSocket clients
    broadcast_task = asyncio.create_task(broadcast_loop())
    yield
    # Dừng các tasks khi ứng dụng shutdown
    broadcast_task.cancel()
    tcp_manager.stop()
    
async def cleanup_stale_connections():
    """Periodically clean up stale connections"""
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            
            stale_timeout = 300  # 5 minutes
            current_time = time.time()
            
            for endpoint_name, connections_list in [
                ("general", ws_connections),
                ("trajectory", trajectory_ws_connections),
                ("motor", motor_ws_connections),
                ("pid", pid_ws_connections),
                ("firmware", firmware_ws_connections),
                ("server", server_ws_connections)
            ]:
                # Create a copy of the list to avoid modification during iteration
                connections_copy = connections_list.copy()
                
                for ws in connections_copy:
                    # Check if this connection is stale
                    last_activity = getattr(ws, "last_activity", 0)
                    if current_time - last_activity > stale_timeout:
                        try:
                            client_id = getattr(ws, "client_id", f"{ws.client.host}:{ws.client.port}")
                            logger.info(f"Closing stale {endpoint_name} connection from {client_id}")
                            
                            # Try to send close message
                            try:
                                await ws.close(code=1000, reason="Stale connection")
                            except:
                                pass
                                
                            # Remove from connection list
                            if ws in connections_list:
                                connections_list.remove(ws)
                        except Exception as e:
                            logger.error(f"Error cleaning up stale connection: {e}")
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in stale connection cleanup: {e}")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # Allow all origins for development
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    # Add this option to allow WebSocket CORS
    max_age=86400  # Cache preflight requests for 24 hours
)

# Store app start time for uptime tracking
app.state.start_time = time.time()

# Add a simple health check route that the frontend can use to verify the server is running
@app.get("/")
def root():
    """Root endpoint for basic connectivity testing"""
    return {
        "status": "online",
        "message": "WebSocket server is running",
        "time": datetime.datetime.now().isoformat(),
    }

# WebSocket

ws_connections = []

# Add these new WebSocket connections dictionaries 
trajectory_ws_connections = []
server_ws_connections = []
pid_ws_connections = []
firmware_ws_connections = []
motor_ws_connections = []

# Add this simple heartbeat function (currently missing)
async def send_simple_heartbeat(ws: WebSocket, endpoint_name: str):
    """Very simple heartbeat with minimal dependencies"""
    try:
        while True:
            await asyncio.sleep(30)  # Simple 30-second interval
            try:
                # Simplest possible message
                await ws.send_text('{"type":"ping"}')
            except Exception:
                # Any error means connection is probably dead
                break
    except asyncio.CancelledError:
        # Normal cancellation - just exit
        pass
    except Exception:
        # Any other error - exit silently
        pass

# Keep the original endpoint for backward compatibility
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await handle_websocket_connection(
        ws, 
        ws_connections, 
        "general"
    )
@app.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    """Special diagnostic websocket endpoint with verbose error reporting"""
    client_id = f"{websocket.client.host}:{websocket.client.port}"
    print(f"⚠️ TEST: Connection attempt from {client_id}")
    
    try:
        print(f"⚠️ TEST: Headers: {websocket.headers}")
        print(f"⚠️ TEST: About to accept connection from {client_id}")
        
        # This is the critical step
        await websocket.accept()
        print(f"✅ TEST: Connection SUCCESSFULLY ACCEPTED from {client_id}")
        
        # Send success message immediately
        await websocket.send_text('{"status":"connected", "message":"Connection successful"}')
        
        # Echo loop with detailed error logging
        while True:
            try:
                data = await websocket.receive_text()
                print(f"📩 TEST received: {data[:100]}")
                await websocket.send_text(data)
            except WebSocketDisconnect:
                print(f"👋 TEST: Client {client_id} disconnected normally")
                break
            except Exception as e:
                print(f"❌ TEST error: {type(e).__name__}: {e}")
                break
    except Exception as e:
        print(f"❌❌ TEST CRITICAL ERROR: {type(e).__name__}: {e}")
# Replace the existing send_heartbeat function
# Change the name to avoid ad blocker detection
@app.get("/api/health-check")  # Changed from "/api/ping"
async def health_check():      # Changed from "ping"
    """Server health check endpoint"""
    return {
        "status": "ok", 
        "time": datetime.datetime.now().isoformat(),
        "message": "Server is running"
    }
# Add a very basic direct WebSocket endpoint
@app.websocket("/ws/test-direct")
async def websocket_test_direct(websocket: WebSocket):
    """Absolute minimum WebSocket handler for testing"""
    try:
        # Accept the connection - only critical step
        await websocket.accept()
        print(f"TEST-DIRECT: Connection accepted from {websocket.client.host}")
        
        # Send a simple welcome message
        await websocket.send_text('{"status":"connected"}')
        
        # Simple message loop
        while True:
            try:
                # Wait for messages with no timeout
                data = await websocket.receive_text()
                # Echo back immediately
                await websocket.send_text(data)
            except Exception:
                # Any error means we should exit the loop
                break
    except Exception as e:
        print(f"TEST-DIRECT error: {e}")

# Add this ultra-simplified endpoint with explicit error handling
@app.websocket("/ws/connect")
async def websocket_connect(websocket: WebSocket):
    """Extremely simplified WebSocket handler with step-by-step logging"""
    print(f"CONNECTION ATTEMPT from {websocket.client.host}:{websocket.client.port}")
    
    try:
        print(f"ACCEPTING CONNECTION...")
        await websocket.accept()
        print(f"CONNECTION ACCEPTED!")
        
        # Send immediate confirmation
        await websocket.send_text('{"status":"connected"}')
        print(f"CONFIRMATION SENT")
        
        # Simple receive loop
        while True:
            try:
                data = await websocket.receive_text()
                print(f"RECEIVED: {data[:50]}")
                await websocket.send_text(data)
            except Exception as e:
                print(f"ERROR IN LOOP: {e}")
                break
    except Exception as e:
        print(f"CRITICAL ERROR: {type(e).__name__}: {e}")

@app.get("/api/network-diagnostics")
async def network_diagnostics():
    """Provide network diagnostics to help troubleshoot connection issues"""
    import socket
    import platform
    import os
    
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    # Get network interfaces
    interfaces = []
    try:
        # Try conditional import
        try:
            import netifaces
            for interface in netifaces.interfaces():
                try:
                    ifaddresses = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in ifaddresses:
                        for link in ifaddresses[netifaces.AF_INET]:
                            interfaces.append({
                                "interface": interface,
                                "ip": link.get('addr', ''),
                                "netmask": link.get('netmask', '')
                            })
                except:
                    pass
        except ImportError:
            # Fallback to socket-based information if netifaces not available
            interfaces.append({
                "interface": "default",
                "ip": local_ip,
                "netmask": "unknown"
            })
    except Exception:
        interfaces = ["Error retrieving network interfaces"]
    
    return {
        "hostname": hostname,
        "local_ip": local_ip,
        "os": platform.system(),
        "platform": platform.platform(),
        "interfaces": interfaces,
        "websocket_endpoints": {
            "/ws/direct": True,
            "/ws/connect": True,
            "/ws/test": True
        },
        "possible_issues": [
            "Firewall blocking WebSocket traffic",
            "Port already in use by another application",
            "Network proxies or VPNs interfering with connections",
            "Browser extensions blocking WebSocket connections",
            "Antivirus software inspecting and blocking connections"
        ],
        "suggested_fixes": [
            "Try a different port (e.g., 8080 instead of 8000)",
            "Try connecting from a different network",
            "Temporarily disable firewall or security software",
            "Try a different browser",
            "Use an incognito/private window"
        ]
    }

async def send_heartbeat(ws: WebSocket, interval: int, endpoint_name: str = ""):
    """Improved heartbeat sender with adaptive failure handling"""
    failure_count = 0
    max_failures = 10  # Increased from 8 to 10
    backoff_factor = 1.0
    
    while True:
        try:
            await asyncio.sleep(interval * backoff_factor)
            
            # Skip heartbeat if recent activity
            current_time = time.time()
            last_activity = getattr(ws, "last_activity", 0)
            
            # If there was activity in the last half interval, skip this heartbeat
            if current_time - last_activity < interval / 2:
                continue
                
            # Create heartbeat with useful metadata
            heartbeat_message = {
                "type": "ping", 
                "timestamp": time.time(),
                "endpoint": endpoint_name,
                "server_time": datetime.datetime.now().isoformat(),
                "id": f"heartbeat_{int(time.time())}"
            }
            
            await ws.send_text(json.dumps(heartbeat_message))
            
            # Only log rare heartbeats to reduce spam
            if failure_count > 0 or random.random() < 0.1:  # Log 10% of heartbeats or after failures
                client_id = getattr(ws, "client_id", f"{ws.client.host}:{ws.client.port}")
                print(f"Heartbeat sent to {endpoint_name} client {client_id}")
            
            # Reset on successful heartbeat
            failure_count = 0
            backoff_factor = 1.0
            
        except asyncio.CancelledError:
            # Normal cancellation during cleanup
            break
        except Exception as e:
            failure_count += 1
            print(f"Heartbeat error for {endpoint_name} client: {e} (failure {failure_count}/{max_failures})")
            
            if failure_count >= max_failures:
                print(f"Too many failures ({failure_count}), stopping heartbeat")
                break
                
            # Exponential backoff to avoid hammering with failures
            backoff_factor = min(2.0, 1.0 + (failure_count * 0.2))
            await asyncio.sleep(interval * 0.3)  # Brief pause before retry


async def process_trajectory_command(data_str, ws):
    """Process trajectory-specific commands"""
    try:
        data = json.loads(data_str)
        command_type = data.get("type")
        
        if command_type == "get_trajectory":
            await send_trajectory_to_one(ws)
        elif command_type == "manual_control":
            # Handle manual control commands for robot movement
            robot_id = data.get("robot_id", "robot01")
            x_speed = data.get("x_speed", 0)
            y_speed = data.get("y_speed", 0)
            theta = data.get("theta", 0)
            
            cmd = f"MOVE:X{x_speed:.2f}Y{y_speed:.2f}R{theta:.2f}"
            result = tcp_manager.send_command(robot_id, cmd)
            
            await ws.send_text(json.dumps({"status": "success", "message": result}))
    except Exception as e:
        await ws.send_text(json.dumps({"status": "error", "message": str(e)}))

async def process_motor_command(data_str, ws):
    """Process motor-specific commands với định dạng JSON chuẩn"""
    try:
        data = json.loads(data_str)
        command_type = data.get("type")
        
        if command_type == "motor_control":
            robot_id = data.get("robot_id", "robot01")
            speeds = data.get("speeds", [0, 0, 0])
            
            # Cập nhật cú pháp lệnh để gửi tới robot
            cmd = f"MOTOR_SPEED:{speeds[0]},{speeds[1]},{speeds[2]}"
            result = tcp_manager.send_command(robot_id, cmd)
            
            # Lưu dữ liệu vào database mới
            db = SessionLocal()
            motor_control = MotorControl(
                command_id=data.get("command_id", f"cmd_{int(time.time()*1000)}"),
                speeds=speeds,
                timestamp=datetime.datetime.now(),
                raw_data=data
            )
            db.add(motor_control)
            db.commit()
            db.close()
            
            await ws.send_text(json.dumps({
                "type": "response",
                "status": "success", 
                "message": result
            }))
            
        elif command_type == "emergency_stop":
            robot_id = data.get("robot_id", "robot01")
            result = tcp_manager.send_command(robot_id, "EMERGENCY_STOP")
            
            # Lưu lệnh khẩn cấp vào database mới
            db = SessionLocal()
            emergency = EmergencyCommand(
                command_id=data.get("command_id", f"stop_{int(time.time()*1000)}"),
                timestamp=datetime.datetime.now(),
                raw_data=data
            )
            db.add(emergency)
            db.commit()
            db.close()
            
            await ws.send_text(json.dumps({
                "type": "response",
                "status": "success",
                "message": "Emergency stop command sent"
            }))
            
    except Exception as e:
        await ws.send_text(json.dumps({
            "type": "response", 
            "status": "error", 
            "message": str(e)
        }))

async def process_pid_command(data_str, ws):
    """Process PID commands với định dạng JSON chuẩn"""
    try:
        data = json.loads(data_str)
        command_type = data.get("type")
        
        if command_type == "pid_update":
            robot_id = data.get("robot_id", "robot01")
            motor_id = data.get("motor_id", 1)
            params = data.get("parameters", {})
            p = params.get("p", 0)
            i = params.get("i", 0)
            d = params.get("d", 0)
            
            cmd = f"MOTOR:{motor_id} Kp:{p} Ki:{i} Kd:{d}"
            result = tcp_manager.send_command(robot_id, cmd)
            
            # Lưu cấu hình PID vào database mới
            db = SessionLocal()
            pid_config = PIDConfig(
                motor_id=motor_id,
                p_value=p,
                i_value=i,
                d_value=d,
                timestamp=datetime.datetime.now(),
                raw_data=data
            )
            db.add(pid_config)
            db.commit()
            db.close()
            
            await ws.send_text(json.dumps({
                "type": "response",
                "status": "success",
                "message": "PID settings updated"
            }))
            
        elif command_type == "get_pid_config":
            motor_id = data.get("motor_id", 1)
            db = SessionLocal()
            pid_data = (
                db.query(PIDConfig)
                .filter(PIDConfig.motor_id == motor_id)
                .order_by(PIDConfig.timestamp.desc())
                .first()
            )
            db.close()
            
            if pid_data:
                await ws.send_text(json.dumps({
                    "type": "pid_update",
                    "motor_id": motor_id,
                    "parameters": {
                        "p": pid_data.p_value,
                        "i": pid_data.i_value,
                        "d": pid_data.d_value
                    },
                    "timestamp": time.time()
                }))
            else:
                await ws.send_text(json.dumps({
                    "type": "pid_update",
                    "motor_id": motor_id,
                    "parameters": {
                        "p": 0,
                        "i": 0,
                        "d": 0
                    },
                    "timestamp": time.time()
                }))
    except Exception as e:
        await ws.send_text(json.dumps({
            "type": "response",
            "status": "error",
            "message": str(e)
        }))

async def process_firmware_command(data_str, ws):
    """Process firmware commands với định dạng JSON chuẩn"""
    try:
        data = json.loads(data_str)
        command_type = data.get("type")
        
        if command_type == "firmware_status":
            # Xử lý yêu cầu cập nhật firmware
            version = data.get("version", "unknown")
            status = data.get("status", "pending")
            progress = data.get("progress", 0)
            
            # Lưu cập nhật vào database
            db = SessionLocal()
            firmware_update = FirmwareUpdate(
                version=version,
                status=status,
                progress=progress,
                timestamp=datetime.datetime.now(),
                raw_data=data
            )
            db.add(firmware_update)
            db.commit()
            db.close()
            
            # Gửi phản hồi            
            await ws.send_text(json.dumps({
                "type": "response",
                "status": "success",
                "message": "Firmware update status recorded"
            }))
            
            # Simulate firmware update progress in background
            if status == "updating":
                asyncio.create_task(simulate_firmware_update(ws, version))
                
        elif command_type == "firmware_request":
            # Trả về thông tin firmware hiện tại
            db = SessionLocal()
            latest_firmware = (
                db.query(FirmwareUpdate)
                .order_by(FirmwareUpdate.timestamp.desc())
                .first()
            )
            db.close()
            
            if latest_firmware:
                await ws.send_text(json.dumps({
                    "type": "firmware_status",
                    "version": latest_firmware.version,
                    "status": latest_firmware.status,
                    "progress": latest_firmware.progress,
                    "timestamp": time.time()
                }))
            else:
                await ws.send_text(json.dumps({
                    "type": "firmware_status",
                    "version": "1.0.0",
                    "status": "idle",
                    "progress": 0,
                    "timestamp": time.time()
                }))
                
    except Exception as e:
        await ws.send_text(json.dumps({
            "type": "response",
            "status": "error",
            "message": str(e)
        }))

async def simulate_firmware_update(ws, version):
    """Mô phỏng quá trình cập nhật firmware và gửi thông báo tiến độ"""
    try:
        for progress in range(10, 101, 10):
            # Cập nhật trạng thái trong database
            db = SessionLocal()
            firmware_update = FirmwareUpdate(
                version=version,
                status="updating" if progress < 100 else "completed",
                progress=progress,
                timestamp=datetime.datetime.now(),
                raw_data={
                    "type": "firmware_status",
                    "version": version,
                    "status": "updating" if progress < 100 else "completed",
                    "progress": progress,
                    "timestamp": time.time()
                }
            )
            db.add(firmware_update)
            db.commit()
            db.close()
            
            # Gửi cập nhật đến client
            await ws.send_text(json.dumps({
                "type": "firmware_status",
                "version": version,
                "status": "updating" if progress < 100 else "completed",
                "progress": progress,
                "timestamp": time.time()
            }))
            
            # Đợi một chút trước khi cập nhật tiếp theo
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Error during firmware update simulation: {e}")

async def process_frontend_command(data_str, ws):
    """Xử lý lệnh từ frontend"""
    try:
        data = json.loads(data_str)
        command_type = data.get("type")
        
        if command_type == "motor_control":
            # Gửi lệnh điều khiển động cơ đến ESP32
            robot_id = data.get("robot_id", "robot01")
            motor_id = data.get("motor_id")
            speed = data.get("speed")
            
            cmd = f"MOTOR_{motor_id}_SPEED:{speed}"
            result = tcp_manager.send_command(robot_id, cmd)
            
            # Lưu lệnh vào database
            db = SessionLocal()
            log = CommandLog(command=cmd)
            db.add(log)
            db.commit()
            db.close()
            
        elif command_type == "pid_control":
            # Gửi cấu hình PID
            robot_id = data.get("robot_id", "robot01")
            motor_id = data.get("motor_id")
            p = data.get("p")
            i = data.get("i")
            d = data.get("d")
            
            cmd = f"MOTOR:{motor_id} Kp:{p} Ki:{i} Kd:{d}"
            result = tcp_manager.send_command(robot_id, cmd)
            
            # Lưu cấu hình PID vào database
            db = SessionLocal()
            pid_config = PIDConfig(
                motor_id=motor_id,
                Kp=p, Ki=i, Kd=d
            )
            db.add(pid_config)
            db.commit()
            db.close()
            
        elif command_type == "emergency_stop":
            # Lệnh dừng khẩn cấp
            robot_id = data.get("robot_id", "robot01")
            result = tcp_manager.send_command(robot_id, "EMERGENCY_STOP")
            
        # Gửi phản hồi về frontend
        await ws.send_text(json.dumps({"status": "success", "message": result}))
        
    except Exception as e:
        await ws.send_text(json.dumps({"status": "error", "message": str(e)}))

async def send_trajectory_to_one(ws: WebSocket):
    db = SessionLocal()
    try:
        # Sửa để sử dụng TrajectoryData hoặc IMUData
        # Ưu tiên sử dụng TrajectoryData nếu có dữ liệu
        trajectory_points = db.query(TrajectoryData).order_by(
            TrajectoryData.timestamp.asc()).all()
        
        if trajectory_points and len(trajectory_points) > 0:
            # Nếu có dữ liệu quỹ đạo trong bảng TrajectoryData
            x_points = []
            y_points = []
            
            # Lấy điểm từ bảng TrajectoryData
            for point in trajectory_points:
                x_points.append(point.current_x)
                y_points.append(point.current_y)
                
            # Đảm bảo số lượng điểm x và y bằng nhau
            min_len = min(len(x_points), len(y_points))
            x_points = x_points[:min_len]
            y_points = y_points[:min_len]
            
            print(f"Sending trajectory data from TrajectoryData: {min_len} points")
            
            data = {
                "type": "trajectory_data",
                "trajectory": {
                    "x": x_points,
                    "y": y_points
                }
            }
            
            await ws.send_text(json.dumps(data))
        else:
            # Gửi dữ liệu trống nếu không có điểm nào
            await ws.send_text(json.dumps({
                "type": "trajectory_data",
                "trajectory": {
                    "x": [],
                    "y": []
                }
            }))
            
    except Exception as e:
        print(f"Error sending trajectory data: {str(e)}")
        # Gửi lỗi
        await ws.send_text(json.dumps({
            "type": "error",
            "message": f"Failed to get trajectory data: {str(e)}"
        }))
    finally:
        db.close()

@app.get("/api/connection-test")
def test_connection():
    """Enhanced connection test endpoint with more diagnostic information"""
    return {
        "status": "online",
        "time": datetime.datetime.now().isoformat(),
        "server_info": {
            "version": "1.2.0",  # Add a version number to track changes
            "uptime": time.time() - getattr(app, "start_time", time.time()),
            "process_id": os.getpid(),
            "platform": sys.platform
        },
        "endpoints": {
            "websocket": [
                "/ws",
                "/ws/trajectory", 
                "/ws/motor", 
                "/ws/pid", 
                "/ws/firmware", 
                "/ws/server"
            ],
            "http": [
                "/api/connection-test",
                "/api/connection-status",
                "/api/connection-details",
                "/api/websocket-test"
            ]
        },
        "active_connections": {
            "general": len(ws_connections),
            "trajectory": len(trajectory_ws_connections),
            "motor": len(motor_ws_connections),
            "pid": len(pid_ws_connections),
            "firmware": len(firmware_ws_connections),
            "server": len(server_ws_connections),
            "total": sum([
                len(ws_connections),
                len(trajectory_ws_connections),
                len(motor_ws_connections),
                len(pid_ws_connections),
                len(firmware_ws_connections),
                len(server_ws_connections)
            ])
        }
    }

async def broadcast_loop():
    while True:
        await broadcast_trajectory()
        await broadcast_motor_data()
        await asyncio.sleep(0.1)  # 10 times per second

async def broadcast_trajectory():
    """Broadcast dữ liệu quỹ đạo đến tất cả clients theo định dạng JSON chuẩn"""
    connections = ws_connections + trajectory_ws_connections
    if not connections:
        return
    
    try:
        # Lấy dữ liệu mới nhất từ bảng mới
        db = SessionLocal()
        
        # Lấy điểm quỹ đạo gần nhất từ bảng TrajectoryData
        latest_trajectory = db.query(TrajectoryData).order_by(
            TrajectoryData.timestamp.desc()).first()
        
        # Lấy điểm quỹ đạo gần nhất để lấy vị trí hiện tại
        latest_imu = db.query(IMUData).order_by(
            IMUData.timestamp.desc()).first()
        
        # Lấy RPM mới nhất cho 3 động cơ từ bảng EncoderData
        latest_encoder = db.query(EncoderData).order_by(
            EncoderData.timestamp.desc()).first()
        
        # Tạo định dạng JSON chuẩn cho dữ liệu quỹ đạo
        trajectory_json = {
            "type": "trajectory_data",
            "timestamp": time.time(),
            "current_position": {
                "x": latest_imu.accel_x if latest_imu else 0,
                "y": latest_imu.accel_y if latest_imu else 0,
                "theta": latest_imu.yaw if latest_imu else 0
            },
            "target_position": {
                "x": latest_trajectory.target_x if latest_trajectory else 0,
                "y": latest_trajectory.target_y if latest_trajectory else 0,
                "theta": latest_trajectory.target_theta if latest_trajectory else 0
            },
            "progress_percent": latest_trajectory.progress_percent if latest_trajectory else 0
        }
        
        # Lấy tối đa 100 điểm gần nhất nếu có 
        if latest_trajectory and latest_trajectory.points:
            trajectory_json["points"] = latest_trajectory.points[:100]
        else:
            # Thêm một điểm mặc định nếu không có dữ liệu
            trajectory_json["points"] = [{"x": 0, "y": 0, "theta": 0}]
        
        # Tạo định dạng JSON chuẩn cho dữ liệu encoder
        encoder_json = {
            "type": "encoder_data",
            "timestamp": time.time(),
            "values": latest_encoder.values if latest_encoder else [0, 0, 0],
            "rpm": latest_encoder.rpm if latest_encoder else [0, 0, 0]
        }
        
        # Đóng gói dữ liệu để gửi đi
        data = {
            "type": "update",
            "trajectory": trajectory_json,
            "encoder": encoder_json
        }
        
        # Broadcast đến tất cả clients
        for ws in connections:
            try:
                await ws.send_text(json.dumps(data))
            except Exception as e:
                print(f"Error sending to client: {e}")
                
        db.close()
    except Exception as e:
        print(f"Lỗi khi broadcast dữ liệu quỹ đạo: {e}")

async def broadcast_motor_data():
    """Broadcast motor data theo định dạng JSON chuẩn"""
    connections = ws_connections + motor_ws_connections
    if not connections:
        return
    
    try:
        db = SessionLocal()
        
        # Lấy dữ liệu encoder và RPM mới nhất
        latest_encoder = db.query(EncoderData).order_by(
            EncoderData.timestamp.desc()).first()
        
        # Tạo định dạng JSON chuẩn
        motor_data = {
            "type": "motor_control",
            "timestamp": time.time(),
            "speeds": latest_encoder.rpm if latest_encoder else [0, 0, 0]
        }
        
        # Broadcast đến tất cả clients
        for ws in connections:
            try:
                await ws.send_text(json.dumps(motor_data))
            except Exception as e:
                print(f"Error sending motor data: {e}")
                
        db.close()
    except Exception as e:
        print(f"Error broadcasting motor data: {e}")

# Add this endpoint to view connection statistics
@app.get("/api/connection-status")
def get_connection_status():
    return {
        "status": "running",
        "active_connections": {
            "general": len(ws_connections),
            "trajectory": len(trajectory_ws_connections),
            "motor": len(motor_ws_connections),
            "pid": len(pid_ws_connections),
            "firmware": len(firmware_ws_connections),
            "server": len(server_ws_connections),
        }
    }

@app.get("/api/connection-details")
def get_connection_details():
    """Endpoint cung cấp thông tin chi tiết về các kết nối WebSocket hiện tại"""
    
    # Hàm helper để lấy thông tin chi tiết từ danh sách kết nối
    def get_connection_info(connections):
        return [
            {
                "host": conn.client.host,
                "port": conn.client.port,
                "id": f"{conn.client.host}:{conn.client.port}",
                "connected_since": getattr(conn, "connected_since", time.time()),
                "last_activity": getattr(conn, "last_activity", None)
            } 
            for conn in connections
        ]
    
    return {
        "timestamp": time.time(),
        "connections": {
            "general": get_connection_info(ws_connections),
            "trajectory": get_connection_info(trajectory_ws_connections),
            "motor": get_connection_info(motor_ws_connections),
            "pid": get_connection_info(pid_ws_connections),
            "firmware": get_connection_info(firmware_ws_connections),
            "server": get_connection_info(server_ws_connections)
        },
        "summary": {
            "total_connections": (
                len(ws_connections) + 
                len(trajectory_ws_connections) + 
                len(motor_ws_connections) + 
                len(pid_ws_connections) + 
                len(firmware_ws_connections) + 
                len(server_ws_connections)
            ),
            "by_endpoint": {
                "general": len(ws_connections),
                "trajectory": len(trajectory_ws_connections),
                "motor": len(motor_ws_connections),
                "pid": len(pid_ws_connections),
                "firmware": len(firmware_ws_connections),
                "server": len(server_ws_connections)
            }
        }
    }

# Add this at the top of the file near other init code
# Initialize JSONDataHandler for storing incoming data
def store_json_message(json_data):
    """Store JSON message to database using JSONDataHandler"""
    db = SessionLocal()
    try:
        result = JSONDataHandler.store_json_message(db, json_data)
        return result is not None
    except Exception as e:
        print(f"Error storing JSON data: {e}")
        return False
    finally:
        db.close()

# Assume this is part of TCPConnectionManager
def process_robot_message(self, message, client_id):
    """Process incoming messages from robot and store in database"""
    try:
        data = json.loads(message)
        
        # Store the message using JSONDataHandler
        store_json_message(data)
        
        # Handle specific message types
        msg_type = data.get("type")
        if msg_type == "encoder_data":
            # Create task to broadcast updated data to clients
            asyncio.create_task(broadcast_motor_data())
        elif msg_type == "trajectory_data":
            # Create task to broadcast updated trajectory
            asyncio.create_task(broadcast_trajectory())
        elif msg_type == "imu_data":
            # Update any UI that needs IMU data
            pass
            
    except json.JSONDecodeError:
        print(f"Received invalid JSON from {client_id}: {message[:100]}")
    except Exception as e:
        print(f"Error processing robot message: {e}")

# Thêm hàm helper để xử lý tất cả endpoint WebSocket một cách nhất quán
async def handle_websocket_connection(ws: WebSocket, connection_list: list, endpoint_name: str, initial_handler=None):
    """Bare minimum WebSocket connection handler"""
    client_id = f"{ws.client.host}:{ws.client.port}"
    print(f"Connection request from {client_id} for {endpoint_name}")
    
    try:
        # 1. ACCEPT CONNECTION - This is the most critical step
        await ws.accept()
        print(f"✅ Accepted {endpoint_name} connection from {client_id}")
        
        # 2. Basic setup - keep metadata simple
        ws.connected_since = time.time()
        ws.last_activity = time.time()
        
        # 3. Add to connection list
        if ws not in connection_list:
            connection_list.append(ws)
        
        # 4. Send basic acknowledgment
        await ws.send_text(json.dumps({"status": "connected"}))
        
        # 5. Simple message loop - no timeouts
        while True:
            try:
                data = await ws.receive_text()
                ws.last_activity = time.time()
                
                # Just echo back for testing
                await ws.send_text(data)
            except WebSocketDisconnect:
                print(f"Client {client_id} disconnected")
                break
            except Exception as e:
                print(f"Error in {endpoint_name} loop: {e}")
                break
    
    except Exception as e:
        print(f"ERROR in {endpoint_name} connection: {e}")
    
    finally:
        # Clean up
        if ws in connection_list:
            connection_list.remove(ws)
        print(f"{endpoint_name} connection closed for {client_id}")

# Cập nhật hàm broadcast_connection_status_change
async def broadcast_connection_status_change(endpoint_name, client_id, status):
    """Broadcast thông báo khi có thay đổi trạng thái kết nối"""
    message = {
        "type": "connection_status_change",
        "timestamp": time.time(),
        "endpoint": endpoint_name,
        "client_id": client_id,
        "status": status,
        "connection_count": {
            "general": len(ws_connections),
            "trajectory": len(trajectory_ws_connections),
            "motor": len(motor_ws_connections),
            "pid": len(pid_ws_connections),
            "firmware": len(firmware_ws_connections),
            "server": len(server_ws_connections)
        }
    }
    
    # Broadcast to all server connections
    success_count = 0
    error_count = 0
    
    for conn in server_ws_connections:
        try:
            await conn.send_text(json.dumps(message))
            success_count += 1
        except Exception as e:
            error_count += 1
            print(f"Error broadcasting connection status to {conn.client.host}:{conn.client.port}: {e}")
    
    if error_count > 0 and success_count == 0:
        print(f"WARNING: Failed to broadcast connection status to ANY clients ({error_count} errors)")

# Thêm hàm này vào main.py
async def process_server_command(data_str, ws):
    """Process server control commands với định dạng JSON chuẩn"""
    try:
        if isinstance(data_str, dict):
            data = data_str  # Already parsed as JSON
        else:
            data = json.loads(data_str)
            
        command_type = data.get("type")
        
        if command_type == "get_status":
            # Trả về thông tin trạng thái server
            await ws.send_text(json.dumps({
                "type": "server_status",
                "status": "running",
                "uptime": time.time() - getattr(app, "start_time", time.time()),
                "connections": {
                    "general": len(ws_connections),
                    "trajectory": len(trajectory_ws_connections),
                    "motor": len(motor_ws_connections),
                    "pid": len(pid_ws_connections),
                    "firmware": len(firmware_ws_connections),
                    "server": len(server_ws_connections)
                },
                "timestamp": time.time()
            }))
        elif command_type == "keep_alive":
            # Đáp ứng yêu cầu keep-alive ngay lập tức
            await ws.send_text(json.dumps({
                "type": "connection_ok",
                "timestamp": time.time()
            }))
        elif command_type == "echo":
            # Phản hồi lại tin nhắn echo để kiểm tra kết nối
            echo_data = {
                "type": "echo_response",
                "original_message": data,
                "timestamp": time.time(),
                "id": data.get("id", "unknown")
            }
            await ws.send_text(json.dumps(echo_data))
            
    except Exception as e:
        await ws.send_text(json.dumps({
            "type": "response",
            "status": "error",
            "message": f"Error processing server command: {str(e)}"
        }))

# Thêm endpoint mới để kiểm tra kết nối
@app.get("/api/websocket-test")
def test_websockets():
    """Endpoint để kiểm tra trạng thái các WebSocket kết nối"""
    # Kiểm tra xem các kết nối có còn hoạt động
    inactive_connections = []
    now = time.time()
    
    for endpoint_name, connections in [
        ("general", ws_connections),
        ("trajectory", trajectory_ws_connections),
        ("motor", motor_ws_connections),
        ("pid", pid_ws_connections),
        ("firmware", firmware_ws_connections),
        ("server", server_ws_connections)
    ]:
        for conn in connections:
            last_activity = getattr(conn, "last_activity", 0)
            if now - last_activity > 60:  # Không hoạt động trong 60 giây
                inactive_connections.append({
                    "endpoint": endpoint_name,
                    "client_id": f"{conn.client.host}:{conn.client.port}",
                    "inactive_for": now - last_activity
                })
    
    return {
        "timestamp": time.time(),
        "active_connections_count": {
            "general": len(ws_connections),
            "trajectory": len(trajectory_ws_connections),
            "motor": len(motor_ws_connections),
            "pid": len(pid_ws_connections),
            "firmware": len(firmware_ws_connections),
            "server": len(server_ws_connections)
        },
        "inactive_connections": inactive_connections,
        "status": "healthy" if not inactive_connections else "warning"
    }

# Add these new helper functions

async def send_ping_with_retry(ws, client_id, endpoint_name):
    """Send a ping with multiple retries to check if client is still alive"""
    for attempt in range(3):  # Try 3 times
        try:
            ping_data = json.dumps({
                "type": "ping",
                "status": "checking" if attempt == 0 else "urgent",
                "timestamp": time.time(),
                "attempt": attempt + 1,
                "id": f"ping_{int(time.time())}_{attempt}"
            })
            
            await ws.send_text(ping_data)
            
            # Wait for response with increasing timeouts
            timeout = 5 + (attempt * 5)  # 5s, 10s, 15s
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=timeout)
                # If we get here, we received a response
                print(f"Received response from {client_id} on ping attempt {attempt+1}")
                return True
            except asyncio.TimeoutError:
                print(f"No response from {client_id} for ping attempt {attempt+1}")
                # Try next attempt
        except Exception as e:
            print(f"Error sending ping to {client_id}: {e}")
            # Move to next attempt
    
    # If we get here, all attempts failed
    return False

async def route_command_to_handler(endpoint_name, data, ws):
    """Route command to appropriate handler based on endpoint"""
    try:
        if endpoint_name == "general":
            await process_frontend_command(data, ws)
        elif endpoint_name == "motor":
            await process_motor_command(data, ws)
        elif endpoint_name == "trajectory":
            await process_trajectory_command(data, ws)
        elif endpoint_name == "pid":
            await process_pid_command(data, ws)
        elif endpoint_name == "firmware":
            await process_firmware_command(data, ws)
        elif endpoint_name == "server":
            await process_server_command(data, ws)
    except Exception as e:
        error_msg = str(e)
        print(f"Error processing command for {endpoint_name}: {error_msg}")
        await ws.send_text(json.dumps({
            "type": "response",
            "status": "error",
            "message": f"Command processing error: {error_msg}"
        }))

# Thêm tất cả các endpoint WebSocket còn thiếu

@app.websocket("/ws/trajectory")
async def trajectory_endpoint(ws: WebSocket):
    await handle_websocket_connection(
        ws, 
        trajectory_ws_connections, 
        "trajectory",
        initial_handler=send_trajectory_to_one
    )

@app.websocket("/ws/motor")
async def motor_endpoint(ws: WebSocket):
    await handle_websocket_connection(
        ws, 
        motor_ws_connections, 
        "motor"
    )

@app.websocket("/ws/server")
async def server_endpoint(ws: WebSocket):
    await handle_websocket_connection(
        ws, 
        server_ws_connections, 
        "server"
    )

@app.websocket("/ws/firmware")
async def firmware_endpoint(ws: WebSocket):
    await handle_websocket_connection(
        ws, 
        firmware_ws_connections, 
        "firmware"
    )

# Đảm bảo endpoint PID đã tồn tại và hoạt động
@app.websocket("/ws/pid")
async def pid_endpoint(ws: WebSocket):
    await handle_websocket_connection(
        ws, 
        pid_ws_connections, 
        "pid"
    )
            
# Simplified WebSocket handler for debugging
@app.websocket("/ws/motor/debug")
async def motor_debug_endpoint(ws: WebSocket):
    """Simple debug endpoint for motor connections"""
    try:
        await ws.accept()
        print("MOTOR DEBUG: Connection accepted")
        
        # Send immediate welcome message
        await ws.send_text(json.dumps({"status": "connected", "endpoint": "motor/debug"}))
        
        while True:
            try:
                data = await ws.receive_text()
                print(f"MOTOR DEBUG received: {data}")
                # Echo back
                await ws.send_text(json.dumps({"type": "echo", "message": data}))
            except WebSocketDisconnect:
                print("MOTOR DEBUG: Client disconnected")
                break
            except Exception as e:
                print(f"MOTOR DEBUG error: {e}")
                break
    except Exception as e:
        print(f"MOTOR DEBUG connection error: {e}")
        # Add this very basic endpoint for testing
@app.websocket("/ws/direct")
async def websocket_direct(websocket: WebSocket):
    """Ultra-minimal WebSocket handler - no error handling, just bare minimum code"""
    print(f"**DIRECT CONNECT** Request from {websocket.client.host}:{websocket.client.port}")
    
    # Accept with minimal surrounding code
    await websocket.accept()
    print(f"**DIRECT CONNECT** Connection ACCEPTED from {websocket.client.host}")
    
    # Send immediate simple confirmation
    await websocket.send_text('{"status":"connected"}')
    
    # Ultra-simple message loop
    while True:
        try:
            # Just echo whatever is received
            data = await websocket.receive_text()
            print(f"**DIRECT CONNECT** Received: {data[:50]}...")
            await websocket.send_text(data)
        except Exception as e:
            print(f"**DIRECT CONNECT** Error: {e}")
            break
if __name__ == "__main__":
    import uvicorn
    # Add logging to see what's happening
    print("Starting server with WebSocket debugging...")
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000,
        log_level="debug",  # Show detailed logs
        ws="websockets"     # Explicitly use websockets library
    )