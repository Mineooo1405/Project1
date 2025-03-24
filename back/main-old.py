import socket
import threading
import numpy as np
import datetime
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import SessionLocal, FirmwareFile, RobotControl, PIDConfig, RPMLLog, TrajectoryLog, CommandLog, IMULog
import matplotlib.pyplot as plt
import io
import json
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio

# Thông số robot
robot_radius = 0.1  # Bán kính robot (m)
wheel_radius = 0.05  # Bán kính bánh xe (m)
x, y, theta = 0, 0, 0  # Vị trí và góc quay ban đầu
dt = 0.1  # Khoảng thời gian cập nhật (s)

def compute_velocity(yaw, omega):
    """Tính vận tốc v_x, v_y dựa trên vận tốc góc của 3 bánh xe."""
    H = np.array([
        [-np.sin(yaw), np.cos(yaw), robot_radius],
        [-np.sin(np.pi / 3 - yaw), -np.cos(np.pi / 3 - yaw), robot_radius],
        [np.sin(np.pi / 3 + yaw), -np.cos(np.pi / 3 + yaw), robot_radius]
    ])
    omega_scaled = np.array(omega) * wheel_radius
    velocities = np.linalg.solve(H, omega_scaled)
    return velocities[0], velocities[1], velocities[2]

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class TCPConnectionManager:
    def __init__(self, host="0.0.0.0", port=5005):
        self.server_host = host
        self.server_port = port
        self.robot_connections = {}  # Lưu kết nối robot {robot_id: socket}
        self.lock = threading.Lock()  # Để xử lý đa luồng an toàn

    def start_tcp_server(self):
        """Khởi động TCP server"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((self.server_host, self.server_port))
        server.listen(10)
        print(f"TCP Server đang chạy trên {self.server_host}:{self.server_port}...")

        while True:
            client_socket, addr = server.accept()
            print(f"🔌 Kết nối mới từ {addr}")

            # Khởi động luồng để xử lý client
            client_handler = threading.Thread(target=self.handle_client, args=(client_socket,))
            client_handler.start()

    def handle_client(self, client_socket):
        """Xử lý từng robot"""
        try:
            client_socket.send("ID?".encode("utf-8"))  # Yêu cầu robot gửi ID
            robot_id = client_socket.recv(1024).decode("utf-8").strip()

            with self.lock:
                self.robot_connections[robot_id] = client_socket
            print(f"Robot {robot_id} đã kết nối.")

            while True:
                data = client_socket.recv(1024).decode("utf-8")
                if not data:
                    break
                print(f"Nhận từ {robot_id}: {data}")

                # Lưu vào database
                try:
                    self.save_to_database(robot_id, data)
                except Exception as e:
                    print(f"Lỗi lưu database: {e}")

        except ConnectionError:
            print(f"Robot {robot_id} mất kết nối.")
        finally:
            with self.lock:
                if robot_id in self.robot_connections:
                    del self.robot_connections[robot_id]
            client_socket.close()
            
tcp_manager = TCPConnectionManager()
threading.Thread(target=tcp_manager.start_tcp_server, daemon=True).start()

# ==============================
# 📌 WebSocket Setup
# ==============================
frontend_ws: WebSocket = None  # Chỉ duy nhất 1 frontend

@app.websocket("/ws/trajectory")
async def websocket_endpoint(websocket: WebSocket):
    """ WebSocket kết nối với Frontend """
    global frontend_ws
    await websocket.accept()
    frontend_ws = websocket
    print("✅ WebSocket Frontend đã kết nối.")

    try:
        while True:
            data = await websocket.receive_text()
            print(f"📡 Nhận dữ liệu từ frontend: {data}")
    except WebSocketDisconnect:
        frontend_ws = None
        print("❌ WebSocket Frontend ngắt kết nối. Chờ kết nối lại...")

async def send_data_to_frontend():
    """ Gửi dữ liệu real-time từ Database lên Frontend """
    global frontend_ws
    if frontend_ws:
        try:
            db = next(get_db())
            logs = db.query(TrajectoryLog).all()
            trajectory_data = {
                "x": [log.x_position for log in logs], 
                "y": [log.y_position for log in logs]
            }
            print("📡 Gửi dữ liệu quỹ đạo đến Frontend:", trajectory_data)  # 🟢 Debug log
            await frontend_ws.send_text(json.dumps(trajectory_data))
        except Exception as e:
            print(f"⚠️ Lỗi gửi dữ liệu WebSocket: {e}")
@app.get("/")
def read_root():
    return {"message": "Robot Control API is running"}

# ==============================
# 📌 ĐIỀU KHIỂN ROBOT
# ==============================

@app.get("/send/{robot_id}/{command}")
async def send_command(robot_id: str, command: str, db: Session = Depends(get_db)):
    response = server.send_command(robot_id, command)

    # Lưu lệnh vào database
    db_command = CommandLog(command=command)
    db.add(db_command)
    db.commit()

    return {"status": response}


# ==============================
# 📌 XỬ LÝ DỮ LIỆU CẢM BIẾN IMU
# ==============================

class IMUData(BaseModel):
    theta: float
    omega_wheel: list[float]
    dt: float

robot_radius = 0.1
wheel_radius = 0.05
x, y, theta = 0, 0, 0

def compute_velocity(theta, omega):
    H = np.array([
        [-np.sin(theta), np.cos(theta), robot_radius],
        [-np.sin(np.pi / 3 - theta), -np.cos(np.pi / 3 - theta), robot_radius],
        [np.sin(np.pi / 3 + theta), -np.cos(np.pi / 3 + theta), robot_radius]
    ])
    omega_scaled = np.array(omega) * wheel_radius
    velocities = np.linalg.solve(H, omega_scaled)
    return velocities[0], velocities[1]

@app.post("/imu_data")
def receive_imu_data(imu: IMUData, db: Session = Depends(get_db)):
    global x, y, theta
    theta = imu.theta

    v_x, v_y = compute_velocity(theta, imu.omega_wheel)

    x += v_x * imu.dt
    y += v_y * imu.dt

    imu_entry = IMULog(
        theta=theta, omega=np.mean(imu.omega_wheel),
        v_x=v_x, v_y=v_y, x_position=x, y_position=y
    )
    db.add(imu_entry)
    db.commit()

    return {"x": x, "y": y, "theta": theta}

@app.get("/imu_data/latest")
def get_latest_imu_data(db: Session = Depends(get_db)):
    latest_imu = db.query(IMULog).order_by(IMULog.timestamp.desc()).first()
    if latest_imu:
        return {
            "x": latest_imu.x_position, "y": latest_imu.y_position, "theta": latest_imu.theta,
            "timestamp": latest_imu.timestamp
        }
    return {"message": "No IMU data available"}

# ==============================
# 📌 QUẢN LÝ PID
# ==============================

class PIDConfigData(BaseModel):
    motor_id: int
    Kp: float
    Ki: float
    Kd: float

@app.post("/set_pid")
def set_pid(pid: PIDConfigData, db: Session = Depends(get_db)):
    pid_entry = PIDConfig(motor_id=pid.motor_id, Kp=pid.Kp, Ki=pid.Ki, Kd=pid.Kd)
    db.add(pid_entry)
    db.commit()
    return {"message": f"PID updated for motor {pid.motor_id}"}

@app.get("/get_pid/{motor_id}")
def get_pid(motor_id: int, db: Session = Depends(get_db)):
    pid_data = db.query(PIDConfig).filter(PIDConfig.motor_id == motor_id).order_by(PIDConfig.last_updated.desc()).first()
    if pid_data:
        return {"motor_id": motor_id, "Kp": pid_data.Kp, "Ki": pid_data.Ki, "Kd": pid_data.Kd}
    return {"message": "No PID data available"}

# ==============================
# 📌 GHI DỮ LIỆU RPM
# ==============================

@app.get("/rpm_logs/latest")
def get_latest_rpm(db: Session = Depends(get_db)):
    latest_rpm = db.query(RPMLLog).order_by(RPMLLog.timestamp.desc()).first()
    if latest_rpm:
        return {"motor_id": latest_rpm.motor_id, "rpm_value": latest_rpm.rpm_value, "timestamp": latest_rpm.timestamp}
    return {"message": "No RPM data available"}

@app.post("/rpm_logs")
def add_rpm_log(motor_id: int, rpm_value: float, db: Session = Depends(get_db)):
    rpm_entry = RPMLLog(motor_id=motor_id, rpm_value=rpm_value)
    db.add(rpm_entry)
    db.commit()
    return {"message": "RPM data stored"}

# ==============================
# 📌 API `POST` Để Gửi Dữ Liệu Quỹ Đạo Robot
# ==============================
class TrajectoryData(BaseModel):
    x_position: float
    y_position: float
    angel: float

@app.post("/trajectory/")
def add_trajectory_data(trajectory: TrajectoryData, db: Session = Depends(get_db)):
    new_entry = TrajectoryLog(
        x_position=trajectory.x_position,
        y_position=trajectory.y_position,
        angel=trajectory.angel,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(new_entry)
    db.commit()
    return {"message": "Trajectory data added successfully"}

# ==============================
# 📌 API `GET` Để Lấy Dữ Liệu Quỹ Đạo
# ==============================
@app.get("/trajectory/")
def get_trajectory(db: Session = Depends(get_db)):
    logs = db.query(TrajectoryLog).all()
    x_data = [log.x_position for log in logs]
    y_data = [log.y_position for log in logs]
    angles = [log.angel for log in logs]
    timestamps = [log.timestamp for log in logs]
    return {"x": x_data, "y": y_data, "theta": angles, "timestamps": timestamps}
# ==============================
# 📌 KHỞI CHẠY API
# ==============================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

