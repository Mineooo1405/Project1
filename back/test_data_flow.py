import asyncio
import websockets
import socket
import json
import time
import argparse
import logging
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for colored console output
init()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"data_flow_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger("data_flow_test")

# Configuration
CONFIG = {
    'tcp_server_host': 'localhost',
    'tcp_server_port': 9000,
    'ws_bridge_host': 'localhost',
    'ws_bridge_port': 9003,
    'backend_host': 'localhost',
    'backend_port': 8000,
    'robot_id': 'test_robot',
    'api_key': '140504'
}

# Test message constants
ROBOT_REGISTRATION = {
    "type": "registration",
    "robot_id": CONFIG['robot_id'],
    "model": "TestRobot",
    "version": "1.0.0",
    "capabilities": ["motor_control", "sensor_data"],
    "timestamp": None  # Will be filled at runtime
}

MOTOR_DATA = {
    "type": "motor_data",
    "robot_id": CONFIG['robot_id'],
    "motors": {
        "left": {"speed": 120, "temperature": 45},
        "right": {"speed": 120, "temperature": 46},
        "arm": {"position": 90, "load": 0.2}
    },
    "timestamp": None  # Will be filled at runtime
}

SENSOR_DATA = {
    "type": "sensor_data",
    "robot_id": CONFIG['robot_id'],
    "sensors": {
        "temperature": 25.5,
        "humidity": 60,
        "pressure": 1013
    },
    "timestamp": None  # Will be filled at runtime
}

MOTOR_CONTROL_COMMAND = {
    "type": "motor_control",
    "robot_id": CONFIG['robot_id'],
    "velocities": {"x": 0.5, "y": 0, "theta": 0.2},
    "frontend": True,
    "timestamp": None  # Will be filled at runtime
}

class SimulatedRobot:
    """Simulates a robot connecting to the TCP server"""
    
    def __init__(self, host='localhost', port=9000, robot_id='test_robot'):
        self.host = host
        self.port = port
        self.robot_id = robot_id
        self.socket = None
        self.connected = False
        self.buffer = ''
        self.received_messages = []
        self.stop_flag = False
        
    def connect(self):
        """Connect to TCP server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.settimeout(0.1)  # Short timeout for non-blocking reads
            self.connected = True
            print(f"{Fore.GREEN}✓ Robot connected to TCP Server ({self.host}:{self.port}){Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Robot connection failed: {e}{Style.RESET_ALL}")
            self.connected = False
            return False
            
    def disconnect(self):
        """Disconnect from TCP server"""
        if self.socket:
            self.socket.close()
        self.connected = False
        self.socket = None
        print(f"{Fore.YELLOW}Robot disconnected from TCP Server{Style.RESET_ALL}")
        
    def send_message(self, message):
        """Send message to TCP server"""
        if not self.connected:
            print(f"{Fore.RED}Cannot send message: Robot not connected{Style.RESET_ALL}")
            return False
            
        try:
            # Add timestamp if not present
            if isinstance(message, dict) and message.get('timestamp') is None:
                message['timestamp'] = time.time()
                
            # Add robot_id if not present
            if isinstance(message, dict) and message.get('robot_id') is None:
                message['robot_id'] = self.robot_id
                
            msg_str = json.dumps(message) + '\n'
            self.socket.sendall(msg_str.encode('utf-8'))
            print(f"{Fore.CYAN}➤ Robot sent: {message.get('type', 'unknown')}{Style.RESET_ALL}")
            logger.info(f"Robot sent: {message}")
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Error sending message from robot: {e}{Style.RESET_ALL}")
            self.connected = False
            return False
            
    def read_message(self):
        """Read message from TCP server (non-blocking)"""
        if not self.connected:
            return None
            
        try:
            # Try to receive data
            data = self.socket.recv(4096)
            if not data:
                # Connection closed by server
                print(f"{Fore.YELLOW}TCP Server closed the connection{Style.RESET_ALL}")
                self.connected = False
                return None
                
            # Add to buffer and process
            self.buffer += data.decode('utf-8')
            
            # Process complete messages
            while '\n' in self.buffer:
                message, self.buffer = self.buffer.split('\n', 1)
                if message.strip():
                    try:
                        msg_json = json.loads(message)
                        self.received_messages.append(msg_json)
                        print(f"{Fore.GREEN}← Robot received: {msg_json.get('type', 'unknown')}{Style.RESET_ALL}")
                        logger.info(f"Robot received: {msg_json}")
                        return msg_json
                    except json.JSONDecodeError:
                        print(f"{Fore.RED}Invalid JSON received: {message}{Style.RESET_ALL}")
                        
            return None
        except socket.timeout:
            # Expected for non-blocking operation
            return None
        except Exception as e:
            print(f"{Fore.RED}✗ Error reading from TCP Server: {e}{Style.RESET_ALL}")
            return None
            
    async def run(self):
        """Run the simulated robot"""
        if not self.connect():
            print(f"{Fore.RED}Failed to connect robot to TCP Server{Style.RESET_ALL}")
            return
            
        # Send registration message
        reg_msg = dict(ROBOT_REGISTRATION)
        reg_msg['timestamp'] = time.time()
        reg_msg['robot_id'] = self.robot_id
        self.send_message(reg_msg)
        
        # Main loop
        while not self.stop_flag:
            # Read incoming messages
            msg = self.read_message()
            
            # If we got a message, process it
            if msg and isinstance(msg, dict):
                # If it's a control command, acknowledge it
                if msg.get('type') == 'motor_control':
                    # Send back motor data as response
                    motor_data = dict(MOTOR_DATA)
                    motor_data['timestamp'] = time.time()
                    motor_data['robot_id'] = self.robot_id
                    # Update with received velocity
                    if 'velocities' in msg:
                        motor_data['motors']['left']['speed'] = abs(int(msg['velocities'].get('x', 0) * 100))
                        motor_data['motors']['right']['speed'] = abs(int(msg['velocities'].get('x', 0) * 100))
                    self.send_message(motor_data)
            
            await asyncio.sleep(0.1)
            
        # Clean up
        self.disconnect()

class SimulatedFrontend:
    """Simulates a frontend connecting to the WebSocket bridge"""
    
    def __init__(self, host='localhost', port=9003):
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False
        self.received_messages = []
        self.stop_flag = False
        
    async def connect(self):
        """Connect to WebSocket bridge"""
        try:
            uri = f"ws://{self.host}:{self.port}"
            self.websocket = await websockets.connect(uri)
            self.connected = True
            print(f"{Fore.GREEN}✓ Frontend connected to WebSocket Bridge ({self.host}:{self.port}){Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Frontend connection failed: {e}{Style.RESET_ALL}")
            self.connected = False
            return False
            
    async def disconnect(self):
        """Disconnect from WebSocket bridge"""
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        self.websocket = None
        print(f"{Fore.YELLOW}Frontend disconnected from WebSocket Bridge{Style.RESET_ALL}")
        
    async def send_message(self, message):
        """Send message to WebSocket bridge"""
        if not self.connected:
            print(f"{Fore.RED}Cannot send message: Frontend not connected{Style.RESET_ALL}")
            return False
            
        try:
            # Add timestamp if not present
            if isinstance(message, dict) and message.get('timestamp') is None:
                message['timestamp'] = time.time()
                
            await self.websocket.send(json.dumps(message))
            print(f"{Fore.CYAN}➤ Frontend sent: {message.get('type', 'unknown')}{Style.RESET_ALL}")
            logger.info(f"Frontend sent: {message}")
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Error sending message from frontend: {e}{Style.RESET_ALL}")
            self.connected = False
            return False
            
    async def read_message(self, timeout=0.1):
        """Read message from WebSocket bridge (with timeout)"""
        if not self.connected:
            return None
            
        try:
            # Try to receive data with timeout
            message = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            try:
                msg_json = json.loads(message)
                self.received_messages.append(msg_json)
                print(f"{Fore.GREEN}← Frontend received: {msg_json.get('type', 'unknown')}{Style.RESET_ALL}")
                logger.info(f"Frontend received: {msg_json}")
                return msg_json
            except json.JSONDecodeError:
                print(f"{Fore.RED}Invalid JSON received by frontend: {message}{Style.RESET_ALL}")
                return None
        except asyncio.TimeoutError:
            # Expected for non-blocking operation
            return None
        except Exception as e:
            print(f"{Fore.RED}✗ Error reading from WebSocket Bridge: {e}{Style.RESET_ALL}")
            return None
            
    async def run(self):
        """Run the simulated frontend"""
        if not await self.connect():
            print(f"{Fore.RED}Failed to connect frontend to WebSocket Bridge{Style.RESET_ALL}")
            return
            
        # Main loop
        while not self.stop_flag:
            # Read incoming messages
            msg = await self.read_message()
            
            # We just collect messages, no special processing here
            await asyncio.sleep(0.1)
            
        # Clean up
        await self.disconnect()

async def test_robot_to_backend():
    """Test data flow: Robot → TCP Server → Backend"""
    print(f"{Fore.BLUE}=" * 70)
    print(f"TEST 1: Robot → TCP Server → Backend")
    print(f"=" * 70)
    print(f"This test verifies that data from the robot is forwarded to the backend.{Style.RESET_ALL}")
    
    # Create a robot
    robot = SimulatedRobot(
        host=CONFIG['tcp_server_host'],
        port=CONFIG['tcp_server_port'],
        robot_id=CONFIG['robot_id']
    )
    
    if not robot.connect():
        return
        
    # Send registration and wait for confirmation
    robot.send_message(ROBOT_REGISTRATION)
    
    # Wait for server response
    print("Waiting for server response...")
    start_time = time.time()
    while time.time() - start_time < 5:
        msg = robot.read_message()
        if msg and msg.get('type') == 'registration_confirmation':
            print(f"{Fore.GREEN}✓ Robot registration confirmed{Style.RESET_ALL}")
            break
        await asyncio.sleep(0.1)
    else:
        print(f"{Fore.YELLOW}⚠ No registration confirmation received within timeout{Style.RESET_ALL}")
    
    # Send sensor data (should be forwarded to backend)
    print("\nSending sensor data (should be forwarded to backend)...")
    sensor_data = dict(SENSOR_DATA)
    sensor_data['timestamp'] = time.time()
    robot.send_message(sensor_data)
    
    # Wait for sensor data acknowledgment
    print("Waiting for sensor data acknowledgment...")
    start_time = time.time()
    while time.time() - start_time < 5:
        msg = robot.read_message()
        if msg and msg.get('type') == 'ack' and msg.get('original_type') == 'sensor_data':
            print(f"{Fore.GREEN}✓ Sensor data acknowledged{Style.RESET_ALL}")
            break
        await asyncio.sleep(0.1)
    else:
        print(f"{Fore.YELLOW}⚠ No sensor data acknowledgment received within timeout{Style.RESET_ALL}")
    
    # Clean up
    robot.disconnect()
    print(f"{Fore.BLUE}Test 1 completed{Style.RESET_ALL}")

async def test_frontend_to_robot():
    """Test data flow: Frontend → TCP Server → Robot"""
    print(f"{Fore.BLUE}=" * 70)
    print(f"TEST 2: Frontend → TCP Server → Robot")
    print(f"=" * 70)
    print(f"This test verifies that commands from frontend are forwarded to the robot.{Style.RESET_ALL}")
    
    # Tạo robot ID đặc biệt cho test này để tránh xung đột
    test_robot_id = f"test_robot_cmd_{int(time.time())}"
    
    # Tạo robot và kết nối trước
    robot = SimulatedRobot(
        host=CONFIG['tcp_server_host'],
        port=CONFIG['tcp_server_port'],
        robot_id=test_robot_id
    )
    
    if not robot.connect():
        return
    
    # Đợi welcome message
    await asyncio.sleep(1)
    welcome = robot.read_message()
    if welcome and welcome.get('type') == 'welcome':
        print(f"{Fore.GREEN}✓ Robot received welcome message{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}⚠ No welcome message received{Style.RESET_ALL}")
    
    # Đăng ký robot với thông tin cụ thể hơn
    print("\nRegistering robot with ID:", test_robot_id)
    registration = {
        "type": "registration",
        "robot_id": test_robot_id,
        "model": "TestRobot",
        "version": "1.0.0",
        "capabilities": ["motor_control", "sensor_data"],
        "debug": True,  # Flag đặc biệt cho debug
        "timestamp": time.time()
    }
    robot.send_message(registration)
    
    # Đợi phản hồi từ server - chấp nhận cả data_ack và registration_confirmation
    print("Waiting for registration response...")
    registration_ok = False
    start_time = time.time()
    while time.time() - start_time < 5:
        msg = robot.read_message()
        if msg:
            print(f"{Fore.CYAN}Robot received: {msg.get('type')}{Style.RESET_ALL}")
            if msg.get('type') in ['registration_confirmation', 'data_ack']:
                registration_ok = True
                print(f"{Fore.GREEN}✓ Registration acknowledged{Style.RESET_ALL}")
                break
        await asyncio.sleep(0.1)
    
    if not registration_ok:
        print(f"{Fore.RED}✗ Registration failed - no acknowledgment{Style.RESET_ALL}")
        robot.disconnect()
        return
    
    # Đợi để đảm bảo đăng ký được xử lý
    await asyncio.sleep(1)
    
    # Kết nối frontend sau khi robot đã đăng ký
    print("\nConnecting frontend to WebSocket Bridge...")
    frontend = SimulatedFrontend(
        host=CONFIG['ws_bridge_host'],
        port=CONFIG['ws_bridge_port']
    )
    
    if not await frontend.connect():
        print(f"{Fore.RED}✗ Frontend connection failed{Style.RESET_ALL}")
        robot.disconnect()
        return
    
    # Đợi welcome message từ WebSocket Bridge
    await asyncio.sleep(1)
    
    # Xây dựng lệnh motor_control với nhiều thông tin hơn
    print("\nSending motor control command from frontend...")
    control_cmd = {
        "type": "motor_control",
        "robot_id": test_robot_id,
        "velocities": {"x": 0.5, "y": 0, "theta": 0.2},
        "frontend": True,  # Flag quan trọng để xác định nguồn tin nhắn
        "command_id": f"cmd_{int(time.time())}",  # ID duy nhất cho lệnh
        "timestamp": time.time()
    }
    await frontend.send_message(control_cmd)
    
    # Đợi phản hồi từ WebSocket Bridge (xác nhận đã gửi)
    print("Waiting for WebSocket Bridge acknowledgment...")
    ws_ack = False
    start_time = time.time()
    while time.time() - start_time < 5:
        ws_msg = await frontend.read_message(timeout=0.5)
        if ws_msg:
            print(f"{Fore.CYAN}Frontend received: {ws_msg.get('type')}{Style.RESET_ALL}")
            if ws_msg.get('type') in ['command_sent', 'data_ack']:
                ws_ack = True
                print(f"{Fore.GREEN}✓ WebSocket Bridge acknowledged command{Style.RESET_ALL}")
                break
        await asyncio.sleep(0.1)
    
    # Đợi thời gian để lệnh được chuyển tiếp
    print("\nWaiting for command to be forwarded to robot...")
    await asyncio.sleep(2)  # Tăng thời gian chờ
    
    # Kiểm tra xem robot có nhận được lệnh không
    received_command = False
    start_time = time.time()
    while time.time() - start_time < 10:  # Tăng timeout lên 10 giây
        msg = robot.read_message()
        if msg:
            print(f"{Fore.CYAN}Robot received message: {msg.get('type')}{Style.RESET_ALL}")
            if msg.get('type') == 'motor_control':
                print(f"{Fore.GREEN}✓ Robot received motor control command{Style.RESET_ALL}")
                received_command = True
                break
        await asyncio.sleep(0.2)  # Tăng thời gian giữa các lần kiểm tra
    
    if not received_command:
        print(f"{Fore.RED}✗ Robot did not receive motor control command within timeout{Style.RESET_ALL}")
        # Tiếp tục test dù không nhận được lệnh để kiểm tra luồng ngược
    
    # Robot gửi dữ liệu motor về
    print("\nRobot sending motor data in response...")
    motor_data = {
        "type": "motor_data",
        "robot_id": test_robot_id,
        "motors": {
            "left": {"speed": 50, "temperature": 45},
            "right": {"speed": 50, "temperature": 46},
        },
        "timestamp": time.time()
    }
    robot.send_message(motor_data)
    
    # Đợi frontend nhận dữ liệu motor
    print("Waiting for frontend to receive motor data...")
    frontend_received = False
    start_time = time.time()
    while time.time() - start_time < 10:  # Tăng timeout lên 10 giây
        try:
            msg = await frontend.read_message(timeout=0.5)
            if msg:
                print(f"{Fore.CYAN}Frontend received: {msg.get('type')}{Style.RESET_ALL}")
                if msg.get('type') == 'motor_data' and msg.get('robot_id') == test_robot_id:
                    print(f"{Fore.GREEN}✓ Frontend received motor data from robot{Style.RESET_ALL}")
                    frontend_received = True
                    break
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Error reading frontend message: {e}{Style.RESET_ALL}")
        await asyncio.sleep(0.2)
    
    if not frontend_received:
        print(f"{Fore.RED}✗ Frontend did not receive motor data within timeout{Style.RESET_ALL}")
    
    # Tổng kết
    print("\nTest 2 Summary:")
    print(f"  {'✓' if received_command else '✗'} Command forwarding (Frontend → Robot): {received_command}")
    print(f"  {'✓' if frontend_received else '✗'} Data forwarding (Robot → Frontend): {frontend_received}")
    
    # Clean up
    robot.disconnect()
    await frontend.disconnect()
    
    success = received_command and frontend_received
    print(f"{Fore.GREEN if success else Fore.YELLOW}Test 2 completed: {'SUCCESS' if success else 'PARTIAL FAILURE'}{Style.RESET_ALL}")

# Chỉnh sửa hàm test_bidirectional_flow
async def test_bidirectional_flow():
    """Test bidirectional data flow between all components"""
    print(f"{Fore.BLUE}=" * 70)
    print(f"TEST 3: Full Bidirectional Data Flow")
    print(f"=" * 70)
    print(f"This test verifies full bidirectional data flow between all components.{Style.RESET_ALL}")
    
    # Create a robot and frontend
    robot = SimulatedRobot(
        host=CONFIG['tcp_server_host'],
        port=CONFIG['tcp_server_port'],
        robot_id=f"{CONFIG['robot_id']}_bidir"  # Use unique ID for this test
    )
    
    # Connect robot first and handle manually
    if not robot.connect():
        print(f"{Fore.RED}Failed to connect robot to TCP Server. Aborting test.{Style.RESET_ALL}")
        return False
        
    # Wait for welcome message
    await asyncio.sleep(0.5)
    welcome = robot.read_message()
    if not welcome or welcome.get('type') != 'welcome':
        print(f"{Fore.YELLOW}No welcome message received from server{Style.RESET_ALL}")
    
    # Send registration and wait for confirmation
    print("Registering robot...")
    reg_msg = dict(ROBOT_REGISTRATION)
    reg_msg['timestamp'] = time.time()
    reg_msg['robot_id'] = robot.robot_id
    robot.send_message(reg_msg)
    
    # Wait for registration confirmation
    reg_confirmed = False
    start_time = time.time()
    while time.time() - start_time < 5:
        msg = robot.read_message()
        if msg and msg.get('type') == 'registration_confirmation':
            reg_confirmed = True
            print(f"{Fore.GREEN}✓ Robot registration confirmed{Style.RESET_ALL}")
            break
        elif msg:
            print(f"{Fore.YELLOW}Received non-confirmation message: {msg.get('type')}{Style.RESET_ALL}")
        await asyncio.sleep(0.1)
    
    if not reg_confirmed:
        print(f"{Fore.YELLOW}⚠ No registration confirmation received. Proceeding anyway.{Style.RESET_ALL}")
    
    # Connect frontend
    frontend = SimulatedFrontend(
        host=CONFIG['ws_bridge_host'],
        port=CONFIG['ws_bridge_port']
    )
    
    if not await frontend.connect():
        print(f"{Fore.RED}Failed to connect frontend to WebSocket Bridge. Aborting test.{Style.RESET_ALL}")
        robot.disconnect()
        return False
    
    # Wait for frontend welcome message
    await asyncio.sleep(0.5)
    
    # 1. Send control command from frontend
    print("\n1. Sending motor control command from frontend...")
    control_cmd = dict(MOTOR_CONTROL_COMMAND)
    control_cmd['timestamp'] = time.time()
    control_cmd['robot_id'] = robot.robot_id  # Use the same robot ID we registered with
    await frontend.send_message(control_cmd)
    
    # Give time for the command to propagate
    print("Waiting for robot to receive command...")
    cmd_received = False
    start_time = time.time()
    while time.time() - start_time < 5:
        msg = robot.read_message()
        if msg and msg.get('type') == 'motor_control':
            cmd_received = True
            print(f"{Fore.GREEN}✓ Robot received command: {msg.get('type')}{Style.RESET_ALL}")
            break
        await asyncio.sleep(0.1)
    
    if not cmd_received:
        print(f"{Fore.YELLOW}⚠ Robot did not receive command within timeout{Style.RESET_ALL}")
    
    # 2. Send sensor data from robot
    print("\n2. Sending sensor data from robot...")
    sensor_data = dict(SENSOR_DATA)
    sensor_data['timestamp'] = time.time()
    sensor_data['robot_id'] = robot.robot_id
    robot.send_message(sensor_data)
    
    # Wait for data to be received by frontend
    print("Waiting for frontend to receive data...")
    data_received = False
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            msg = await asyncio.wait_for(frontend.read_message(timeout=0.5), timeout=0.6)
            if msg and msg.get('type') == 'sensor_data':
                data_received = True
                print(f"{Fore.GREEN}✓ Frontend received data: {msg.get('type')}{Style.RESET_ALL}")
                break
        except (asyncio.TimeoutError, Exception):
            pass
        await asyncio.sleep(0.1)
    
    if not data_received:
        print(f"{Fore.YELLOW}⚠ Frontend did not receive data within timeout{Style.RESET_ALL}")
    
    # 3. Check results
    print("\n3. Test Results:")
    print(f"  {'✓' if cmd_received else '✗'} Robot received control command: {cmd_received}")
    print(f"  {'✓' if data_received else '✗'} Frontend received sensor data: {data_received}")
    
    # Clean up
    robot.disconnect()
    await frontend.disconnect()
    
    success = cmd_received and data_received
    print(f"{Fore.GREEN if success else Fore.YELLOW}Test 3 completed: {'SUCCESS' if success else 'PARTIAL FAILURE'}{Style.RESET_ALL}")
    return success

async def main():
    parser = argparse.ArgumentParser(description='Test WebDashboard data flow')
    parser.add_argument('--test', choices=['robot_to_backend', 'frontend_to_robot', 'bidirectional', 'all'],
                      default='all', help='Which test to run')
    parser.add_argument('--robot-id', default=CONFIG['robot_id'], help='Robot ID to use')
    parser.add_argument('--tcp-host', default=CONFIG['tcp_server_host'], help='TCP Server host')
    parser.add_argument('--tcp-port', type=int, default=CONFIG['tcp_server_port'], help='TCP Server port')
    parser.add_argument('--ws-host', default=CONFIG['ws_bridge_host'], help='WebSocket Bridge host')
    parser.add_argument('--ws-port', type=int, default=CONFIG['ws_bridge_port'], help='WebSocket Bridge port')
    
    args = parser.parse_args()
    
    # Update configuration
    CONFIG['robot_id'] = args.robot_id
    CONFIG['tcp_server_host'] = args.tcp_host
    CONFIG['tcp_server_port'] = args.tcp_port
    CONFIG['ws_bridge_host'] = args.ws_host
    CONFIG['ws_bridge_port'] = args.ws_port
    
    print(f"{Fore.BLUE}WebDashboard Data Flow Test")
    print(f"Configuration:")
    for key, value in CONFIG.items():
        print(f"  {key}: {value}")
    print(f"{Style.RESET_ALL}")
    
    # Run requested tests
    if args.test in ['robot_to_backend', 'all']:
        await test_robot_to_backend()
        
    if args.test in ['frontend_to_robot', 'all']:
        await test_frontend_to_robot()
        
    if args.test in ['bidirectional', 'all']:
        await test_bidirectional_flow()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"{Fore.YELLOW}\nTest interrupted by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}\nError during test: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()