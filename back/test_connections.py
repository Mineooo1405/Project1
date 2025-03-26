
import asyncio
import websockets
import socket
import json
import time
import argparse
import sys
import traceback
import logging
import os
from datetime import datetime
import requests

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("connection_test.log")
    ]
)
logger = logging.getLogger("connection_test")

# Cấu hình mặc định
CONFIG = {
    'ws_bridge_host': 'localhost',
    'ws_bridge_port': 9003,
    'tcp_server_host': 'localhost',
    'tcp_server_port': 9000,
    'ws_server_host': 'localhost',
    'ws_server_port': 9002,
    'backend_host': 'localhost',
    'backend_port': 8000,
    'robot_id': 'test_robot',
    'api_key': '140504'
}

class ColorFormatter:
    """Class để định dạng văn bản có màu sắc"""
    HEADER = '\033[95m'
    INFO = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

    @staticmethod
    def header(text):
        return f"{ColorFormatter.HEADER}{ColorFormatter.BOLD}{text}{ColorFormatter.ENDC}"
    
    @staticmethod
    def info(text):
        return f"{ColorFormatter.INFO}{text}{ColorFormatter.ENDC}"
    
    @staticmethod
    def success(text):
        return f"{ColorFormatter.SUCCESS}{text}{ColorFormatter.ENDC}"
    
    @staticmethod
    def warning(text):
        return f"{ColorFormatter.WARNING}{text}{ColorFormatter.ENDC}"
    
    @staticmethod
    def error(text):
        return f"{ColorFormatter.ERROR}{text}{ColorFormatter.ENDC}"
    
    @staticmethod
    def bold(text):
        return f"{ColorFormatter.BOLD}{text}{ColorFormatter.ENDC}"

async def test_frontend_to_ws_bridge():
    """Kiểm tra kết nối từ Frontend đến WebSocket Bridge"""
    print(ColorFormatter.header("\n=== TEST 1: Frontend -> WebSocket Bridge ==="))
    
    uri = f"ws://{CONFIG['ws_bridge_host']}:{CONFIG['ws_bridge_port']}"
    print(f"Kết nối đến WebSocket Bridge: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(ColorFormatter.success("✓ Kết nối thành công đến WebSocket Bridge"))
            
            # Gửi tin nhắn get_motor_data
            msg = {
                "type": "get_motor_data",
                "robot_id": CONFIG['robot_id'],
                "frontend": True,
                "timestamp": time.time()
            }
            
            print(f"Gửi tin nhắn: {msg}")
            await websocket.send(json.dumps(msg))
            print(ColorFormatter.success("✓ Đã gửi tin nhắn đến WebSocket Bridge"))
            
            # Đợi phản hồi
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(ColorFormatter.success(f"✓ Nhận phản hồi: {response}"))
                return True
            except asyncio.TimeoutError:
                print(ColorFormatter.warning("⚠ Không nhận được phản hồi sau 5 giây"))
                return False
            
    except ConnectionRefusedError:
        print(ColorFormatter.error("✗ Kết nối bị từ chối. WebSocket Bridge có thể không hoạt động"))
        return False
    except Exception as e:
        print(ColorFormatter.error(f"✗ Lỗi: {e}"))
        traceback.print_exc()
        return False

async def test_tcp_server_direct():
    """Kiểm tra kết nối trực tiếp đến TCP Server"""
    print(ColorFormatter.header("\n=== TEST 2: Kết Nối Trực Tiếp Đến TCP Server ==="))
    
    host = CONFIG['tcp_server_host']
    port = CONFIG['tcp_server_port']
    print(f"Kết nối đến TCP Server: {host}:{port}")
    
    try:
        # Tạo socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        
        # Kết nối
        sock.connect((host, port))
        print(ColorFormatter.success("✓ Kết nối thành công đến TCP Server"))
        
        # Đọc welcome message
        try:
            welcome_data = sock.recv(4096)
            if welcome_data:
                welcome_msg = welcome_data.decode('utf-8').strip()
                print(ColorFormatter.success(f"✓ Nhận welcome message: {welcome_msg}"))
        except socket.timeout:
            print(ColorFormatter.warning("⚠ Không nhận được welcome message (timeout)"))
        
        # Gửi tin nhắn test
        test_msg = {
            "type": "get_motor_data",
            "robot_id": CONFIG['robot_id'],
            "frontend": True,
            "timestamp": time.time()
        }
        
        message_str = json.dumps(test_msg) + '\n'
        print(f"Gửi tin nhắn: {test_msg}")
        sock.sendall(message_str.encode('utf-8'))
        print(ColorFormatter.success("✓ Đã gửi tin nhắn đến TCP Server"))
        
        # Đọc phản hồi
        try:
            sock.settimeout(5.0)
            response = sock.recv(4096)
            if response:
                response_str = response.decode('utf-8').strip()
                print(ColorFormatter.success(f"✓ Nhận phản hồi: {response_str}"))
                success = True
            else:
                print(ColorFormatter.warning("⚠ Nhận được phản hồi rỗng"))
                success = False
        except socket.timeout:
            print(ColorFormatter.warning("⚠ Không nhận được phản hồi sau 5 giây"))
            success = False
            
        # Đóng kết nối
        sock.close()
        print(ColorFormatter.info("Đã đóng kết nối"))
        
        return success
        
    except ConnectionRefusedError:
        print(ColorFormatter.error(f"✗ Kết nối bị từ chối. TCP Server có thể không hoạt động trên {host}:{port}"))
        return False
    except Exception as e:
        print(ColorFormatter.error(f"✗ Lỗi: {e}"))
        traceback.print_exc()
        return False

async def test_robot_to_ws_server():
    """Kiểm tra kết nối từ Robot đến WebSocket Server"""
    print(ColorFormatter.header("\n=== TEST 3: Robot -> WebSocket Server ==="))
    
    uri = f"ws://{CONFIG['ws_server_host']}:{CONFIG['ws_server_port']}"
    print(f"Kết nối đến WebSocket Server: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(ColorFormatter.success("✓ Kết nối thành công đến WebSocket Server"))
            
            # Đăng ký robot
            registration_msg = {
                "type": "registration",
                "robot_id": CONFIG['robot_id'],
                "model": "TestRobot",
                "version": "1.0.0",
                "capabilities": ["motor_control", "sensor_data"],
                "timestamp": time.time()
            }
            
            print(f"Gửi đăng ký robot: {registration_msg}")
            await websocket.send(json.dumps(registration_msg))
            print(ColorFormatter.success("✓ Đã gửi đăng ký robot"))
            
            # Đợi phản hồi đăng ký
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(ColorFormatter.success(f"✓ Nhận phản hồi đăng ký: {response}"))
            except asyncio.TimeoutError:
                print(ColorFormatter.warning("⚠ Không nhận được phản hồi đăng ký sau 5 giây"))
            
            # Gửi dữ liệu cảm biến
            sensor_data = {
                "type": "sensor_data",
                "robot_id": CONFIG['robot_id'],
                "sensors": {
                    "temperature": 25.5,
                    "humidity": 60,
                    "pressure": 1013
                },
                "timestamp": time.time()
            }
            
            print(f"Gửi dữ liệu cảm biến: {sensor_data}")
            await websocket.send(json.dumps(sensor_data))
            print(ColorFormatter.success("✓ Đã gửi dữ liệu cảm biến"))
            
            # Chờ lệnh từ server (nếu có)
            print("Đợi lệnh từ server (5 giây)...")
            try:
                command = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(ColorFormatter.success(f"✓ Nhận lệnh từ server: {command}"))
                return True
            except asyncio.TimeoutError:
                print(ColorFormatter.info("Không nhận được lệnh từ server sau 5 giây (có thể bình thường)"))
                return True
            
    except ConnectionRefusedError:
        print(ColorFormatter.error("✗ Kết nối bị từ chối. WebSocket Server có thể không hoạt động"))
        return False
    except Exception as e:
        print(ColorFormatter.error(f"✗ Lỗi: {e}"))
        traceback.print_exc()
        return False

async def test_backend_connection():
    """Kiểm tra kết nối đến Backend FastAPI"""
    print(ColorFormatter.header("\n=== TEST 4: Kết nối đến Backend FastAPI ==="))
    
    # Kiểm tra health check API
    health_url = f"http://{CONFIG['backend_host']}:{CONFIG['backend_port']}/api/health-check"
    print(f"Kiểm tra health check API: {health_url}")
    
    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            print(ColorFormatter.success(f"✓ Health check API OK: {response.text}"))
        else:
            print(ColorFormatter.warning(f"⚠ Health check API trả về status code: {response.status_code}"))
            print(f"Response: {response.text}")
        
        # Thử kết nối WebSocket đến backend
        uri = f"ws://{CONFIG['backend_host']}:{CONFIG['backend_port']}/ws/robot/{CONFIG['robot_id']}"
        headers = {
            "Authorization": f"Bearer {CONFIG['api_key']}",
            "Origin": f"http://{CONFIG['backend_host']}:{CONFIG['backend_port']}",
            "X-Robot-ID": CONFIG['robot_id']
        }
        
        print(f"Kết nối WebSocket đến Backend: {uri}")
        print(f"Headers: {headers}")
        
        try:
            async with websockets.connect(uri, extra_headers=headers) as websocket:
                print(ColorFormatter.success("✓ Kết nối WebSocket đến Backend thành công"))
                
                # Gửi heartbeat
                heartbeat = {
                    "type": "heartbeat",
                    "robot_id": CONFIG['robot_id'],
                    "timestamp": time.time()
                }
                
                print(f"Gửi heartbeat đến Backend: {heartbeat}")
                await websocket.send(json.dumps(heartbeat))
                print(ColorFormatter.success("✓ Đã gửi heartbeat đến Backend"))
                
                # Đợi phản hồi
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    print(ColorFormatter.success(f"✓ Nhận phản hồi từ Backend: {response}"))
                    return True
                except asyncio.TimeoutError:
                    print(ColorFormatter.warning("⚠ Không nhận được phản hồi sau 5 giây"))
                    return False
                
        except ConnectionRefusedError:
            print(ColorFormatter.error("✗ Kết nối WebSocket bị từ chối. Backend FastAPI có thể không hỗ trợ WebSocket"))
            return False
        except Exception as e:
            print(ColorFormatter.error(f"✗ Lỗi kết nối WebSocket đến Backend: {e}"))
            traceback.print_exc()
            return False
            
    except requests.exceptions.ConnectionError:
        print(ColorFormatter.error(f"✗ Không thể kết nối đến Backend FastAPI: {health_url}"))
        return False
    except Exception as e:
        print(ColorFormatter.error(f"✗ Lỗi: {e}"))
        traceback.print_exc()
        return False

async def simulate_robot_traffic():
    """Mô phỏng giao thông dữ liệu từ robot để kiểm tra toàn bộ luồng"""
    print(ColorFormatter.header("\n=== TEST 5: Mô phỏng Giao Thông Dữ liệu Robot ==="))
    
    uri = f"ws://{CONFIG['ws_server_host']}:{CONFIG['ws_server_port']}"
    print(f"Kết nối robot đến WebSocket Server: {uri}")
    
    try:
        async with websockets.connect(uri) as robot_ws:
            print(ColorFormatter.success("✓ Kết nối robot thành công"))
            
            # Đăng ký robot
            registration_msg = {
                "type": "registration",
                "robot_id": CONFIG['robot_id'],
                "model": "SimulationRobot",
                "version": "1.0.0",
                "capabilities": ["motor_control", "sensor_data", "camera"],
                "timestamp": time.time()
            }
            
            print("Đăng ký robot...")
            await robot_ws.send(json.dumps(registration_msg))
            
            # Mở kết nối frontend
            frontend_uri = f"ws://{CONFIG['ws_bridge_host']}:{CONFIG['ws_bridge_port']}"
            print(f"Kết nối frontend đến WebSocket Bridge: {frontend_uri}")
            
            async with websockets.connect(frontend_uri) as frontend_ws:
                print(ColorFormatter.success("✓ Kết nối frontend thành công"))
                
                # Gửi lệnh điều khiển từ frontend
                motor_control = {
                    "type": "motor_control",
                    "robot_id": CONFIG['robot_id'],
                    "velocities": {"x": 0.5, "y": 0, "theta": 0.2},
                    "frontend": True,
                    "timestamp": time.time()
                }
                
                print("Gửi lệnh điều khiển motor từ frontend...")
                await frontend_ws.send(json.dumps(motor_control))
                
                # Đợi nhận lệnh từ robot
                print("Đợi robot nhận lệnh...")
                try:
                    robot_command = await asyncio.wait_for(robot_ws.recv(), timeout=5.0)
                    print(ColorFormatter.success(f"✓ Robot nhận lệnh: {robot_command}"))
                    
                    # Robot phản hồi với dữ liệu motor
                    robot_data = {
                        "type": "motor_data",
                        "robot_id": CONFIG['robot_id'],
                        "motors": {
                            "left": {"speed": 120, "temperature": 45},
                            "right": {"speed": 120, "temperature": 46},
                            "arm": {"position": 90, "load": 0.2}
                        },
                        "timestamp": time.time()
                    }
                    
                    print("Robot gửi dữ liệu motor...")
                    await robot_ws.send(json.dumps(robot_data))
                    
                    # Đợi frontend nhận dữ liệu
                    print("Đợi frontend nhận dữ liệu...")
                    try:
                        frontend_data = await asyncio.wait_for(frontend_ws.recv(), timeout=5.0)
                        print(ColorFormatter.success(f"✓ Frontend nhận dữ liệu: {frontend_data}"))
                        print(ColorFormatter.success("✓ Mô phỏng giao thông dữ liệu hoàn tất thành công!"))
                        return True
                    except asyncio.TimeoutError:
                        print(ColorFormatter.warning("⚠ Frontend không nhận được dữ liệu sau 5 giây"))
                        return False
                    
                except asyncio.TimeoutError:
                    print(ColorFormatter.warning("⚠ Robot không nhận được lệnh sau 5 giây"))
                    return False
                
    except Exception as e:
        print(ColorFormatter.error(f"✗ Lỗi mô phỏng giao thông dữ liệu: {e}"))
        traceback.print_exc()
        return False

async def run_all_tests():
    """Chạy tất cả các bài kiểm tra"""
    print(ColorFormatter.header("\n======= KIỂM TRA KẾT NỐI HỆ THỐNG ROBOT ======="))
    print(f"Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Cấu hình:")
    for key, value in CONFIG.items():
        print(f"  - {key}: {value}")
    print("=" * 50)
    
    results = {}
    
    # Test 1
    results["frontend_to_ws_bridge"] = await test_frontend_to_ws_bridge()
    
    # Test 2
    results["tcp_server_direct"] = await test_tcp_server_direct()
    
    # Test 3
    results["robot_to_ws_server"] = await test_robot_to_ws_server()
    
    # Test 4
    results["backend_connection"] = await test_backend_connection()
    
    # Test 5
    results["simulate_robot_traffic"] = await simulate_robot_traffic()
    
    # Tổng hợp kết quả
    print(ColorFormatter.header("\n======= KẾT QUẢ KIỂM TRA ======="))
    
    success_count = 0
    total_count = len(results)
    
    for test_name, result in results.items():
        status = ColorFormatter.success("✓ PASS") if result else ColorFormatter.error("✗ FAIL")
        print(f"{test_name}: {status}")
        if result:
            success_count += 1
    
    success_rate = (success_count / total_count) * 100
    print(f"\nTỷ lệ thành công: {success_count}/{total_count} ({success_rate:.1f}%)")
    
    if success_count == total_count:
        print(ColorFormatter.success("\nTẤT CẢ CÁC KIỂM TRA ĐỀU THÀNH CÔNG! Hệ thống kết nối hoạt động tốt."))
    else:
        print(ColorFormatter.warning("\nMỘT SỐ KIỂM TRA THẤT BẠI. Kiểm tra logs để biết thêm chi tiết."))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Kiểm tra kết nối hệ thống robot')
    parser.add_argument('--test', choices=['all', 'frontend', 'tcp', 'robot', 'backend', 'simulate'], 
                        default='all', help='Chọn kiểm tra cụ thể để chạy')
    parser.add_argument('--ws-bridge-host', default=CONFIG['ws_bridge_host'], help='WebSocket Bridge host')
    parser.add_argument('--ws-bridge-port', type=int, default=CONFIG['ws_bridge_port'], help='WebSocket Bridge port')
    parser.add_argument('--tcp-host', default=CONFIG['tcp_server_host'], help='TCP Server host')
    parser.add_argument('--tcp-port', type=int, default=CONFIG['tcp_server_port'], help='TCP Server port')
    parser.add_argument('--ws-host', default=CONFIG['ws_server_host'], help='WebSocket Server host')
    parser.add_argument('--ws-port', type=int, default=CONFIG['ws_server_port'], help='WebSocket Server port')
    parser.add_argument('--backend-host', default=CONFIG['backend_host'], help='Backend host')
    parser.add_argument('--backend-port', type=int, default=CONFIG['backend_port'], help='Backend port')
    parser.add_argument('--robot-id', default=CONFIG['robot_id'], help='ID của robot')
    parser.add_argument('--api-key', default=CONFIG['api_key'], help='API Key cho backend')
    
    args = parser.parse_args()
    
    # Cập nhật cấu hình
    CONFIG['ws_bridge_host'] = args.ws_bridge_host
    CONFIG['ws_bridge_port'] = args.ws_bridge_port
    CONFIG['tcp_server_host'] = args.tcp_host
    CONFIG['tcp_server_port'] = args.tcp_port
    CONFIG['ws_server_host'] = args.ws_host
    CONFIG['ws_server_port'] = args.ws_port
    CONFIG['backend_host'] = args.backend_host
    CONFIG['backend_port'] = args.backend_port
    CONFIG['robot_id'] = args.robot_id
    CONFIG['api_key'] = args.api_key
    
    # Chạy bài kiểm tra
    if args.test == 'all':
        asyncio.run(run_all_tests())
    elif args.test == 'frontend':
        asyncio.run(test_frontend_to_ws_bridge())
    elif args.test == 'tcp':
        asyncio.run(test_tcp_server_direct())
    elif args.test == 'robot':
        asyncio.run(test_robot_to_ws_server())
    elif args.test == 'backend':
        asyncio.run(test_backend_connection())
    elif args.test == 'simulate':
        asyncio.run(simulate_robot_traffic())