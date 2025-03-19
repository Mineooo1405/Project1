import asyncio
import websockets
import json
import time
import random

async def simulate_robot_data():
    """Giả lập dữ liệu từ robot và gửi đến backend"""
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        print("Đã kết nối với WebSocket server")
        
        # Ping-pong để duy trì kết nối
        async def heartbeat():
            while True:
                try:
                    await asyncio.sleep(25)
                    await websocket.send(json.dumps({"type": "pong"}))
                    print("Sent heartbeat")
                except:
                    break
        
        # Khởi động heartbeat trong nền
        heartbeat_task = asyncio.create_task(heartbeat())
        
        try:
            # Test 1: Gửi dữ liệu encoder giả lập
            for i in range(5):
                encoder_data = {
                    "type": "encoder_data",
                    "values": [random.randint(1000, 2000) for _ in range(3)],
                    "rpm": [random.randint(50, 150) for _ in range(3)],
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(encoder_data))
                print(f"Đã gửi encoder data: {encoder_data}")
                
                # Đợi và nhận phản hồi
                response = await websocket.recv()
                print(f"Nhận phản hồi: {response}")
                await asyncio.sleep(1)
            
            # Test 2: Gửi dữ liệu IMU giả lập
            for i in range(5):
                imu_data = {
                    "type": "imu_data",
                    "orientation": {
                        "roll": random.uniform(-10, 10),
                        "pitch": random.uniform(-10, 10),
                        "yaw": random.uniform(0, 360)
                    },
                    "acceleration": {
                        "x": random.uniform(-1, 1),
                        "y": random.uniform(-1, 1),
                        "z": random.uniform(9.7, 9.9)
                    },
                    "angular_velocity": {
                        "x": random.uniform(-0.1, 0.1),
                        "y": random.uniform(-0.1, 0.1),
                        "z": random.uniform(-0.1, 0.1)
                    },
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(imu_data))
                print(f"Đã gửi IMU data: {imu_data}")
                
                # Đợi và nhận phản hồi
                response = await websocket.recv()
                print(f"Nhận phản hồi: {response}")
                await asyncio.sleep(1)
                
            # Test 3: Nhận bản tin broadcast từ server
            print("Lắng nghe broadcast từ server...")
            for i in range(5):
                broadcast = await websocket.recv()
                print(f"Nhận broadcast từ server: {broadcast[:200]}...")
                await asyncio.sleep(1)
                
        finally:
            heartbeat_task.cancel()
            
async def test_control_commands():
    """Test gửi lệnh điều khiển từ frontend tới backend"""
    uri = "ws://localhost:8000/ws/motor"
    async with websockets.connect(uri) as websocket:
        print("Đã kết nối với Motor WebSocket endpoint")
        
        # Đợi tin nhắn khởi tạo từ server
        init_msg = await websocket.recv()
        print(f"Nhận tin khởi tạo: {init_msg}")
        
        # Test 1: Gửi lệnh motor_control
        for i in range(3):
            command = {
                "type": "motor_control",
                "robot_id": "test_robot",
                "speeds": [random.randint(-100, 100) for _ in range(3)],
                "command_id": f"test_cmd_{int(time.time()*1000)}"
            }
            await websocket.send(json.dumps(command))
            print(f"Đã gửi lệnh motor_control: {command}")
            
            # Đợi phản hồi
            response = await websocket.recv()
            print(f"Nhận phản hồi: {response}")
            await asyncio.sleep(1)
        
        # Test 2: Gửi lệnh emergency_stop
        command = {
            "type": "emergency_stop",
            "robot_id": "test_robot",
            "command_id": f"stop_{int(time.time()*1000)}"
        }
        await websocket.send(json.dumps(command))
        print(f"Đã gửi lệnh emergency_stop: {command}")
        
        # Đợi phản hồi
        response = await websocket.recv()
        print(f"Nhận phản hồi: {response}")

async def test_pid_settings():
    """Test gửi cấu hình PID từ frontend tới backend"""
    uri = "ws://localhost:8000/ws/pid"
    async with websockets.connect(uri) as websocket:
        print("Đã kết nối với PID WebSocket endpoint")
        
        # Test: Gửi lệnh pid_update
        for motor_id in range(1, 4):
            command = {
                "type": "pid_update",
                "robot_id": "test_robot",
                "motor_id": motor_id,
                "parameters": {
                    "p": round(random.uniform(0.1, 1.0), 2),
                    "i": round(random.uniform(0.01, 0.5), 2),
                    "d": round(random.uniform(0.0, 0.1), 2)
                }
            }
            await websocket.send(json.dumps(command))
            print(f"Đã gửi cấu hình PID: {command}")
            
            # Đợi phản hồi
            response = await websocket.recv()
            print(f"Nhận phản hồi: {response}")
            await asyncio.sleep(1)
            
        # Test: Lấy cấu hình PID hiện tại
        for motor_id in range(1, 4):
            command = {
                "type": "get_pid_config",
                "motor_id": motor_id
            }
            await websocket.send(json.dumps(command))
            print(f"Đã gửi lệnh get_pid_config cho động cơ {motor_id}")
            
            # Đợi phản hồi
            response = await websocket.recv()
            print(f"Nhận cấu hình PID: {response}")
            await asyncio.sleep(1)

async def main():
    print("Bắt đầu test WebSocket...")
    
    # Test 1: Giả lập robot data
    await simulate_robot_data()
    
    # Test 2: Gửi lệnh điều khiển 
    await test_control_commands()
    
    # Test 3: Gửi cấu hình PID
    await test_pid_settings()
    
    print("Hoàn thành test WebSocket!")

if __name__ == "__main__":
    asyncio.run(main())