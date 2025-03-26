import asyncio
import websockets
import socket
import json
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_direct")

# Test configuration
TCP_SERVER = ("localhost", 9000)
WS_BRIDGE = "ws://localhost:9003"
TEST_ROBOT_ID = f"test_robot_{int(time.time())}"

class TestRobot:
    """Test robot that connects via TCP"""
    
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.socket = None
        self.buffer = ""
        self.robot_id = TEST_ROBOT_ID
        
    def connect(self):
        """Connect to TCP server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            logger.info(f"Robot connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Robot connection failed: {e}")
            return False
            
    def send_message(self, message):
        """Send a message to the server"""
        if not self.socket:
            logger.error("Robot not connected")
            return False
            
        # Add robot_id if not present
        if isinstance(message, dict) and "robot_id" not in message:
            message["robot_id"] = self.robot_id
            
        # Add timestamp if not present
        if isinstance(message, dict) and "timestamp" not in message:
            message["timestamp"] = time.time()
            
        try:
            message_str = json.dumps(message) + "\n"
            self.socket.sendall(message_str.encode("utf-8"))
            logger.info(f"Robot sent: {message}")
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
            
    def receive(self, timeout=5):
        """Receive data with timeout"""
        if not self.socket:
            logger.error("Robot not connected")
            return None
            
        try:
            self.socket.settimeout(timeout)
            data = self.socket.recv(4096)
            if not data:
                logger.warning("Server closed connection")
                return None
                
            self.buffer += data.decode("utf-8")
            
            # Process complete messages
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                if not line.strip():
                    continue
                    
                try:
                    message = json.loads(line)
                    logger.info(f"Robot received: {message}")
                    return message
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON: {line}")
                    
            return None
        except socket.timeout:
            # Expected for non-blocking operation
            return None
        except Exception as e:
            logger.error(f"Error receiving data: {e}")
            return None
            
    def close(self):
        """Close connection"""
        if self.socket:
            self.socket.close()
            self.socket = None
            logger.info("Robot disconnected")

class TestFrontend:
    """Test frontend that connects via WebSocket"""
    
    def __init__(self, uri):
        self.uri = uri
        self.websocket = None
        
    async def connect(self):
        """Connect to WebSocket bridge"""
        try:
            self.websocket = await websockets.connect(self.uri)
            logger.info(f"Frontend connected to {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Frontend connection failed: {e}")
            return False
            
    async def send_message(self, message):
        """Send a message to the server"""
        if not self.websocket:
            logger.error("Frontend not connected")
            return False
            
        # Add timestamp if not present
        if isinstance(message, dict) and "timestamp" not in message:
            message["timestamp"] = time.time()
            
        # Add frontend flag
        if isinstance(message, dict) and "frontend" not in message:
            message["frontend"] = True
            
        try:
            await self.websocket.send(json.dumps(message))
            logger.info(f"Frontend sent: {message}")
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
            
    async def receive(self, timeout=5):
        """Receive data with timeout"""
        if not self.websocket:
            logger.error("Frontend not connected")
            return None
            
        try:
            message = await asyncio.wait_for(self.websocket.recv(), timeout)
            try:
                data = json.loads(message)
                logger.info(f"Frontend received: {data}")
                return data
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON: {message}")
                return None
        except asyncio.TimeoutError:
            # Expected for timeout
            return None
        except Exception as e:
            logger.error(f"Error receiving data: {e}")
            return None
            
    async def close(self):
        """Close connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("Frontend disconnected")

async def test_communication():
    """Test direct communication between robot and frontend"""
    # Connect robot to TCP server
    robot = TestRobot(*TCP_SERVER)
    if not robot.connect():
        return False
        
    # Read welcome message
    welcome = robot.receive()
    if not welcome or welcome.get("type") != "welcome":
        logger.error("No welcome message received")
        robot.close()
        return False
        
    # Register robot
    registration = {
        "type": "registration",
        "robot_id": TEST_ROBOT_ID,
        "model": "TestModel",
        "version": "1.0.0",
        "capabilities": ["test"],
        "debug": True
    }
    robot.send_message(registration)
    
    # Wait for registration confirmation
    reg_response = robot.receive(timeout=5)
    if not reg_response or reg_response.get("type") not in ["registration_confirmation", "data_ack"]:
        logger.error("Registration failed")
        robot.close()
        return False
    
    # Connect frontend to WebSocket Bridge
    frontend = TestFrontend(WS_BRIDGE)
    if not await frontend.connect():
        robot.close()
        return False
    
    # Wait for welcome message
    frontend_welcome = await frontend.receive(timeout=5)
    
    # Send command from frontend to robot
    command = {
        "type": "test_command",
        "robot_id": TEST_ROBOT_ID,
        "data": "test data",
        "timestamp": time.time()
    }
    await frontend.send_message(command)
    
    # Wait for robot to receive command
    logger.info("Waiting for robot to receive command...")
    cmd_received = False
    for _ in range(10):
        msg = robot.receive(timeout=1)
        if msg and msg.get("type") == "test_command":
            cmd_received = True
            logger.info("✓ Robot received command from frontend")
            break
            
    # Send data from robot to frontend
    sensor_data = {
        "type": "test_data",
        "robot_id": TEST_ROBOT_ID,
        "value": 42,
        "timestamp": time.time()
    }
    robot.send_message(sensor_data)
    
    # Wait for frontend to receive data
    logger.info("Waiting for frontend to receive data...")
    data_received = False
    for _ in range(10):
        try:
            msg = await frontend.receive(timeout=1)
            if msg and msg.get("type") == "test_data":
                data_received = True
                logger.info("✓ Frontend received data from robot")
                break
        except:
            await asyncio.sleep(0.5)
            
    # Clean up
    robot.close()
    await frontend.close()
    
    # Print results
    logger.info(f"Command forwarding (Frontend → Robot): {'✓' if cmd_received else '✗'}")
    logger.info(f"Data forwarding (Robot → Frontend): {'✓' if data_received else '✗'}")
    
    return cmd_received and data_received

async def main():
    logger.info("Starting direct communication test")
    success = await test_communication()
    logger.info(f"Test {'succeeded' if success else 'failed'}")

if __name__ == "__main__":
    asyncio.run(main())