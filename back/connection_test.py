#!/usr/bin/env python3

import asyncio
import websockets
import json
import time
import socket
import aiohttp
import random
import argparse
import logging
import sys
import signal
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from colorama import init, Fore, Style

# Khởi tạo colorama để hỗ trợ màu trong terminal
init()

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"connection_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger("connection_test")

# Cấu hình mặc định
DEFAULT_CONFIG = {
    "frontend_ws_url": "ws://localhost:9003",
    "tcp_server_host": "localhost",
    "tcp_server_port": 9000,
    "robot_ws_url": "ws://localhost:9002",
    "backend_url": "http://localhost:8000",
    "backend_ws_url": "ws://localhost:8000/ws/robot/",
    "api_key": "140504",
    "robot_id": "test_robot"
}

# Biến toàn cục để theo dõi các kết nối
connections = {
    "frontend": False,
    "tcp": False,
    "robot": False,
    "backend": False
}

# Tạo ID duy nhất cho phiên kiểm tra
SESSION_ID = f"test_{int(time.time())}"

class ConnectionTester:
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG
        self.robot_id = self.config["robot_id"]
        self.frontend_ws = None
        self.robot_ws = None
        self.tcp_socket = None
        self.backend_session = None
        self.backend_ws = None
        self.running = False
        self.test_data = {}
        self.msg_counters = {
            "frontend_sent": 0,
            "frontend_received": 0,
            "tcp_sent": 0,
            "tcp_received": 0,
            "robot_sent": 0,
            "robot_received": 0,
            "backend_sent": 0,
            "backend_received": 0
        }

    def print_header(self, title: str):
        """In header với màu sắc"""
        print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "="*50)
        print(f" {title}")
        print("="*50 + f"{Style.RESET_ALL}\n")

    def print_success(self, message: str):
        """In thông báo thành công với màu xanh lá"""
        print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")

    def print_error(self, message: str):
        """In thông báo lỗi với màu đỏ"""
        print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")

    def print_warning(self, message: str):
        """In thông báo cảnh báo với màu vàng"""
        print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")

    def print_info(self, message: str):
        """In thông tin với màu xanh dương"""
        print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")

    def print_status(self):
        """In trạng thái kết nối hiện tại"""
        print("\n" + "="*30)
        print("TRẠNG THÁI KẾT NỐI:")
        
        for name, status in connections.items():
            status_str = f"{Fore.GREEN}Connected{Style.RESET_ALL}" if status else f"{Fore.RED}Disconnected{Style.RESET_ALL}"
            print(f"  {name.ljust(8)}: {status_str}")
        
        print("="*30)
        print(f"Tin nhắn gửi/nhận:")
        print(f"  Frontend: {self.msg_counters['frontend_sent']} sent, {self.msg_counters['frontend_received']} received")
        print(f"  TCP:      {self.msg_counters['tcp_sent']} sent, {self.msg_counters['tcp_received']} received")
        print(f"  Robot:    {self.msg_counters['robot_sent']} sent, {self.msg_counters['robot_received']} received")
        print(f"  Backend:  {self.msg_counters['backend_sent']} sent, {self.msg_counters['backend_received']} received")
        print("="*30 + "\n")

    async def connect_frontend(self):
        """Kết nối WebSocket giả lập frontend"""
        try:
            self.print_info(f"Đang kết nối đến WebSocket Bridge: {self.config['frontend_ws_url']}")
            self.frontend_ws = await websockets.connect(self.config['frontend_ws_url'])
            connections["frontend"] = True
            self.print_success("Kết nối WebSocket Bridge thành công")
            return True
        except Exception as e:
            self.print_error(f"Lỗi kết nối đến WebSocket Bridge: {e}")
            connections["frontend"] = False
            return False

    async def connect_tcp_server(self):
        """Kết nối trực tiếp đến TCP Server"""
        try:
            self.print_info(f"Đang kết nối đến TCP Server: {self.config['tcp_server_host']}:{self.config['tcp_server_port']}")
            
            # Tạo TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5.0)
            self.tcp_socket.connect((self.config['tcp_server_host'], self.config['tcp_server_port']))
            
            # Đọc welcome message
            welcome_data = self.tcp_socket.recv(4096).decode('utf-8').strip()
            try:
                welcome = json.loads(welcome_data)
                self.print_info(f"TCP Server welcome: {json.dumps(welcome, indent=2)}")
            except:
                self.print_info(f"TCP Server welcome (raw): {welcome_data}")
            
            connections["tcp"] = True
            self.print_success("Kết nối TCP Server thành công")
            return True
        except Exception as e:
            self.print_error(f"Lỗi kết nối đến TCP Server: {e}")
            connections["tcp"] = False
            return False

    async def connect_robot(self):
        """Kết nối WebSocket giả lập robot"""
        try:
            self.print_info(f"Đang kết nối đến WebSocket Robot: {self.config['robot_ws_url']}")
            self.robot_ws = await websockets.connect(self.config['robot_ws_url'])
            
            # Đăng ký robot
            registration = {
                "type": "register",
                "robot_id": self.robot_id,
                "name": f"Test Robot {SESSION_ID}",
                "model": "Test Model",
                "version": "1.0.0",
                "timestamp": time.time()
            }
            
            await self.robot_ws.send(json.dumps(registration))
            self.msg_counters["robot_sent"] += 1
            self.print_info(f"Đã gửi đăng ký robot: {registration}")
            
            # Đợi xác nhận đăng ký
            try:
                response = await asyncio.wait_for(self.robot_ws.recv(), timeout=5.0)
                self.msg_counters["robot_received"] += 1
                response_data = json.loads(response)
                self.print_info(f"Đã nhận xác nhận đăng ký: {response_data}")
            except asyncio.TimeoutError:
                self.print_warning("Không nhận được xác nhận đăng ký (timeout)")
            
            connections["robot"] = True
            self.print_success("Kết nối Robot thành công")
            return True
        except Exception as e:
            self.print_error(f"Lỗi kết nối Robot: {e}")
            connections["robot"] = False
            return False

    async def connect_backend(self):
        """Kiểm tra kết nối đến backend FastAPI"""
        try:
            # Tạo HTTP session
            self.backend_session = aiohttp.ClientSession()
            
            # Kiểm tra health check endpoint
            self.print_info(f"Kiểm tra health check API: {self.config['backend_url']}/api/health-check")
            async with self.backend_session.get(f"{self.config['backend_url']}/api/health-check") as response:
                if response.status == 200:
                    data = await response.json()
                    self.print_success(f"Backend API hoạt động: {data}")
                    connections["backend"] = True
                else:
                    self.print_error(f"Backend API trả về lỗi: {response.status}")
                    connections["backend"] = False
            
            # Kết nối WebSocket đến backend
            self.print_info(f"Đang kết nối đến Backend WebSocket: {self.config['backend_ws_url']}{self.robot_id}")
            headers = {
                "Authorization": f"Bearer {self.config['api_key']}",
                "Origin": self.config['backend_url'],
                "X-Robot-ID": self.robot_id
            }
            
            try:
                self.backend_ws = await websockets.connect(
                    f"{self.config['backend_ws_url']}{self.robot_id}", 
                    extra_headers=headers
                )
                self.print_success("Kết nối Backend WebSocket thành công")
            except Exception as e:
                self.print_error(f"Lỗi kết nối Backend WebSocket: {e}")
            
            return connections["backend"]
        except Exception as e:
            self.print_error(f"Lỗi kết nối đến backend: {e}")
            connections["backend"] = False
            return False
        
    async def test_frontend_to_tcp(self):
        """Kiểm tra gửi dữ liệu từ Frontend đến TCP Server"""
        if not self.frontend_ws:
            self.print_error("Không có kết nối frontend")
            return False
            
        try:
            message = {
                "type": "test_message",
                "robot_id": self.robot_id,
                "data": f"Test từ Frontend {SESSION_ID}",
                "timestamp": time.time()
            }
            
            self.print_info(f"Đang gửi tin nhắn từ Frontend đến TCP Server...")
            start_time = time.time()
            await self.frontend_ws.send(json.dumps(message))
            self.msg_counters["frontend_sent"] += 1
            
            # Đợi phản hồi
            try:
                response = await asyncio.wait_for(self.frontend_ws.recv(), timeout=5.0)
                elapsed = time.time() - start_time
                self.msg_counters["frontend_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ TCP Server qua WebSocket Bridge sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except asyncio.TimeoutError:
                self.print_error("Không nhận được phản hồi từ TCP Server (timeout)")
                return False
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi tin nhắn từ Frontend: {e}")
            return False

    async def test_tcp_to_robot(self):
        """Kiểm tra gửi dữ liệu từ TCP Server đến Robot"""
        if not self.tcp_socket:
            self.print_error("Không có kết nối TCP")
            return False
            
        try:
            # Gửi lệnh từ TCP Server đến Robot
            command = {
                "type": "command",
                "robot_id": self.robot_id,
                "command": "test_command",
                "data": f"Test từ TCP Server {SESSION_ID}",
                "timestamp": time.time()
            }
            
            self.print_info(f"Đang gửi lệnh từ TCP Server đến Robot...")
            start_time = time.time()
            
            # Chuyển thành JSON string và thêm newline
            command_str = json.dumps(command) + '\n'
            self.tcp_socket.sendall(command_str.encode('utf-8'))
            self.msg_counters["tcp_sent"] += 1
            
            # Đọc phản hồi
            try:
                self.tcp_socket.settimeout(5.0)
                response = self.tcp_socket.recv(4096).decode('utf-8').strip()
                elapsed = time.time() - start_time
                self.msg_counters["tcp_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ TCP Server sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except socket.timeout:
                self.print_error("Không nhận được phản hồi từ TCP Server (timeout)")
                return False
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi lệnh từ TCP Server đến Robot: {e}")
            return False

    async def test_robot_to_tcp(self):
        """Kiểm tra gửi dữ liệu từ Robot đến TCP Server"""
        if not self.robot_ws:
            self.print_error("Không có kết nối robot")
            return False
            
        try:
            # Gửi dữ liệu từ Robot đến TCP Server
            data = {
                "type": "sensor_data",
                "robot_id": self.robot_id,
                "data": {
                    "temperature": random.uniform(20, 30),
                    "humidity": random.uniform(40, 60),
                    "battery": random.uniform(70, 100),
                    "session": SESSION_ID
                },
                "timestamp": time.time()
            }
            
            self.print_info(f"Đang gửi dữ liệu từ Robot đến TCP Server...")
            start_time = time.time()
            await self.robot_ws.send(json.dumps(data))
            self.msg_counters["robot_sent"] += 1
            
            # Đợi phản hồi hoặc tin nhắn tiếp theo
            try:
                response = await asyncio.wait_for(self.robot_ws.recv(), timeout=5.0)
                elapsed = time.time() - start_time
                self.msg_counters["robot_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ TCP Server sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except asyncio.TimeoutError:
                self.print_warning("Không nhận được phản hồi từ TCP Server (có thể bình thường)")
                return True  # Vẫn coi là thành công vì robot có thể không nhận được phản hồi
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi dữ liệu từ Robot: {e}")
            return False
    
    async def test_backend_connection(self):
        """Kiểm tra kết nối đến backend FastAPI"""
        if not self.backend_ws:
            self.print_error("Không có kết nối backend WebSocket")
            return False
            
        try:
            # Gửi dữ liệu đến backend
            data = {
                "type": "status_update",
                "robot_id": self.robot_id,
                "status": "testing",
                "data": {
                    "session": SESSION_ID,
                    "timestamp": time.time()
                }
            }
            
            self.print_info(f"Đang gửi dữ liệu đến Backend...")
            start_time = time.time()
            await self.backend_ws.send(json.dumps(data))
            self.msg_counters["backend_sent"] += 1
            
            # Đợi phản hồi
            try:
                response = await asyncio.wait_for(self.backend_ws.recv(), timeout=5.0)
                elapsed = time.time() - start_time
                self.msg_counters["backend_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ Backend sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except asyncio.TimeoutError:
                self.print_warning("Không nhận được phản hồi từ Backend (có thể bình thường)")
                return True
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi dữ liệu đến Backend: {e}")
            return False

    async def test_full_flow(self):
        """Kiểm tra luồng đầy đủ: Frontend -> TCP -> Robot -> TCP -> Backend"""
        self.print_header("KIỂM TRA LUỒNG ĐẦY ĐỦ")
        
        # Kiểm tra kết nối trước
        if not all([connections["frontend"], connections["tcp"], connections["robot"], connections["backend"]]):
            self.print_warning("Không phải tất cả các kết nối đều đã sẵn sàng. Kết quả có thể không chính xác.")
        
        # Tạo ID duy nhất cho luồng kiểm tra này
        flow_id = f"flow_{int(time.time())}"
        self.print_info(f"Flow ID: {flow_id}")
        
        # Bước 1: Frontend gửi lệnh đến TCP Server
        self.print_info("1. Frontend gửi lệnh đến TCP Server...")
        command = {
            "type": "motor_control",
            "robot_id": self.robot_id,
            "velocities": {
                "x": random.uniform(-1, 1),
                "y": random.uniform(-1, 1),
                "theta": random.uniform(-1, 1)
            },
            "flow_id": flow_id,
            "frontend": True,
            "timestamp": time.time()
        }
        
        try:
            await self.frontend_ws.send(json.dumps(command))
            self.msg_counters["frontend_sent"] += 1
            self.print_success("Đã gửi lệnh từ Frontend")
        except Exception as e:
            self.print_error(f"Lỗi gửi lệnh từ Frontend: {e}")
            return False
            
        # Bước 2: Đợi robot nhận được lệnh từ TCP Server
        self.print_info("2. Đợi Robot nhận lệnh từ TCP Server...")
        
        try:
            received_robot_command = False
            robot_command = None
            
            # Đợi tối đa 10 giây
            start_time = time.time()
            while time.time() - start_time < 10 and not received_robot_command:
                try:
                    message = await asyncio.wait_for(self.robot_ws.recv(), timeout=1.0)
                    self.msg_counters["robot_received"] += 1
                    
                    data = json.loads(message)
                    if data.get("flow_id") == flow_id:
                        received_robot_command = True
                        robot_command = data
                        self.print_success(f"Robot đã nhận lệnh từ TCP Server sau {time.time() - start_time:.2f}s")
                    else:
                        self.print_info("Robot nhận tin nhắn khác (không phải flow hiện tại)")
                        
                except asyncio.TimeoutError:
                    pass
                    
            if not received_robot_command:
                self.print_error("Robot không nhận được lệnh sau 10 giây")
                return False
        except Exception as e:
            self.print_error(f"Lỗi đợi Robot nhận lệnh: {e}")
            return False
            
        # Bước 3: Robot phản hồi trạng thái lên TCP Server
        self.print_info("3. Robot gửi phản hồi đến TCP Server...")
        
        robot_response = {
            "type": "motor_status",
            "robot_id": self.robot_id,
            "status": "executing",
            "original_command": robot_command,
            "flow_id": flow_id,
            "timestamp": time.time()
        }
        
        try:
            await self.robot_ws.send(json.dumps(robot_response))
            self.msg_counters["robot_sent"] += 1
            self.print_success("Robot đã gửi phản hồi đến TCP Server")
        except Exception as e:
            self.print_error(f"Lỗi khi Robot gửi phản hồi: {e}")
            return False
        
        # Bước 4: Đợi frontend nhận phản hồi từ TCP Server
        self.print_info("4. Đợi Frontend nhận phản hồi từ TCP Server...")
        
        try:
            received_frontend_response = False
            frontend_response = None
            
            # Đợi tối đa 10 giây
            start_time = time.time()
            while time.time() - start_time < 10 and not received_frontend_response:
                try:
                    message = await asyncio.wait_for(self.frontend_ws.recv(), timeout=1.0)
                    self.msg_counters["frontend_received"] += 1
                    
                    data = json.loads(message)
                    # Kiểm tra nếu đây là phản hồi cho flow hiện tại
                    if data.get("flow_id") == flow_id or (data.get("original_command") and data.get("original_command").get("flow_id") == flow_id):
                        received_frontend_response = True
                        frontend_response = data
                        self.print_success(f"Frontend đã nhận phản hồi sau {time.time() - start_time:.2f}s")
                    else:
                        self.print_info("Frontend nhận tin nhắn khác (không phải flow hiện tại)")
                        
                except asyncio.TimeoutError:
                    pass
                    
            if not received_frontend_response:
                self.print_warning("Frontend không nhận được phản hồi sau 10 giây")
                # Không return False vì phản hồi có thể không được gửi về frontend
        except Exception as e:
            self.print_error(f"Lỗi đợi Frontend nhận phản hồi: {e}")
        
        # Kiểm tra kết nối backend nếu có
        if connections["backend"] and self.backend_ws:
            # Bước 5: Kiểm tra xem dữ liệu có được chuyển tiếp đến backend không
            self.print_info("5. Kiểm tra Backend nhận dữ liệu...")
            
            try:
                received_backend_data = False
                
                # Đợi tối đa 10 giây
                start_time = time.time()
                while time.time() - start_time < 10 and not received_backend_data:
                    try:
                        message = await asyncio.wait_for(self.backend_ws.recv(), timeout=1.0)
                        self.msg_counters["backend_received"] += 1
                        
                        data = json.loads(message)
                        # Kiểm tra nếu có liên quan đến flow_id
                        if str(data).find(flow_id) != -1:
                            received_backend_data = True
                            self.print_success(f"Backend đã nhận dữ liệu liên quan đến flow sau {time.time() - start_time:.2f}s")
                            self.print_info(f"Dữ liệu: {json.dumps(data, indent=2)}")
                        else:
                            self.print_info("Backend nhận tin nhắn khác (không liên quan đến flow)")
                            
                    except asyncio.TimeoutError:
                        pass
                        
                if not received_backend_data:
                    self.print_warning("Backend không nhận được dữ liệu liên quan sau 10 giây")
            except Exception as e:
                self.print_error(f"Lỗi kiểm tra dữ liệu backend: {e}")
        
        self.print_header("KẾT QUẢ KIỂM TRA LUỒNG")
        self.print_success("Đã hoàn thành kiểm tra luồng dữ liệu")
        self.print_status()
        return True

    async def listen_robot_messages(self):
        """Lắng nghe tin nhắn từ Robot WebSocket"""
        if not self.robot_ws:
            return
            
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.robot_ws.recv(), timeout=1.0)
                    self.msg_counters["robot_received"] += 1
                    data = json.loads(message)
                    
                    # Chỉ log với level debug để tránh spam
                    logger.debug(f"[ROBOT RECV] {data}")
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Lỗi nhận tin nhắn từ Robot: {e}")
                    # Đợi một chút trước khi thử lại
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Lỗi trong listen_robot_messages: {e}")

    async def listen_frontend_messages(self):
        """Lắng nghe tin nhắn từ Frontend WebSocket"""
        if not self.frontend_ws:
            return
            
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.frontend_ws.recv(), timeout=1.0)
                    self.msg_counters["frontend_received"] += 1
                    data = json.loads(message)
                    
                    # Chỉ log với level debug để tránh spam
                    logger.debug(f"[FRONTEND RECV] {data}")
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Lỗi nhận tin nhắn từ Frontend: {e}")
                    # Đợi một chút trước khi thử lại
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Lỗi trong listen_frontend_messages: {e}")

    async def listen_backend_messages(self):
        """Lắng nghe tin nhắn từ Backend WebSocket"""
        if not self.backend_ws:
            return
            
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.backend_ws.recv(), timeout=1.0)
                    self.msg_counters["backend_received"] += 1
                    data = json.loads(message)
                    
                    # Chỉ log với level debug để tránh spam
                    logger.debug(f"[BACKEND RECV] {data}")
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Lỗi nhận tin nhắn từ Backend: {e}")
                    # Đợi một chút trước khi thử lại
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Lỗi trong listen_backend_messages: {e}")

    async def send_heartbeats(self):
        """Gửi heartbeat định kỳ để giữ kết nối"""
        while self.running:
            try:
                # Gửi heartbeat từ robot
                if self.robot_ws and connections["robot"]:
                    heartbeat = {
                        "type": "heartbeat",
                        "robot_id": self.robot_id,
                        "timestamp": time.time()
                    }
                    await self.robot_ws.send(json.dumps(heartbeat))
                    self.msg_counters["robot_sent"] += 1
                    logger.debug(f"Đã gửi heartbeat từ Robot")
                
                # Đợi 30 giây trước lần gửi tiếp theo
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Lỗi gửi heartbeat: {e}")
                await asyncio.sleep(5)

    async def close_all_connections(self):
        """Đóng tất cả các kết nối"""
        self.running = False
        
        # Đóng robot WebSocket
        if self.robot_ws:
            try:
                await self.robot_ws.close()
                self.print_info("Đã đóng kết nối Robot WebSocket")
            except:
                pass
        
        # Đóng frontend WebSocket
        if self.frontend_ws:
            try:
                await self.frontend_ws.close()
                self.print_info("Đã đóng kết nối Frontend WebSocket")
            except:
                pass
        
        # Đóng backend WebSocket
        if self.backend_ws:
            try:
                await self.backend_ws.close()
                self.print_info("Đã đóng kết nối Backend WebSocket")
            except:
                pass
        
        # Đóng backend HTTP session
        if self.backend_session:
            try:
                await self.backend_session.close()
                self.print_info("Đã đóng kết nối Backend HTTP Session")
            except:
                pass
        
        # Đóng TCP socket
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
                self.print_info("Đã đóng kết nối TCP Socket")
            except:
                pass
        
        # Reset trạng thái kết nối
        for key in connections:
            connections[key] = False

    async def run_test(self, test_type="all"):
        """
        Chạy các bài kiểm tra
        
        Args:
            test_type: Loại kiểm tra cần chạy (all, frontend, tcp, robot, backend, flow)
        """
        self.running = True
        
        # Khởi tạo các task lắng nghe
        tasks = []
        
        try:
            self.print_header("KHỞI TẠO KẾT NỐI")
            
            # Kết nối đến các dịch vụ
            if test_type in ["all", "frontend", "flow"]:
                await self.connect_frontend()
                
            if test_type in ["all", "tcp", "flow"]:
                await self.connect_tcp_server()
                
            if test_type in ["all", "robot", "flow"]:
                await self.connect_robot()
                
            if test_type in ["all", "backend", "flow"]:
                await self.connect_backend()
            
            # Khởi động các task lắng nghe nếu cần thiết cho kiểm tra flow
            if test_type in ["all", "flow", "continuous"]:
                if self.robot_ws:
                    robot_listener = asyncio.create_task(self.listen_robot_messages())
                    tasks.append(robot_listener)
                    
                if self.frontend_ws:
                    frontend_listener = asyncio.create_task(self.listen_frontend_messages())
                    tasks.append(frontend_listener)
                    
                if self.backend_ws:
                    backend_listener = asyncio.create_task(self.listen_backend_messages())
                    tasks.append(backend_listener)
                
                # Task gửi heartbeat
                heartbeat_task = asyncio.create_task(self.send_heartbeats())
                tasks.append(heartbeat_task)
            
            # In trạng thái kết nối
            self.print_status()
            
            # Chạy các bài kiểm tra cụ thể
            if test_type == "frontend" and connections["frontend"]:
                self.print_header("KIỂM TRA FRONTEND -> TCP SERVER")
                await self.test_frontend_to_tcp()
                
            elif test_type == "tcp" and connections["tcp"]:
                self.print_header("KIỂM TRA TCP SERVER -> ROBOT")
                await self.test_tcp_to_robot()
                
            elif test_type == "robot" and connections["robot"]:
                self.print_header("KIỂM TRA ROBOT -> TCP SERVER")
                await self.test_robot_to_tcp()
                
            elif test_type == "backend" and connections["backend"]:
                self.print_header("KIỂM TRA TCP SERVER -> BACKEND")
                await self.test_backend_connection()
                
            elif test_type == "flow":
                await self.test_full_flow()
                
            elif test_type == "all":
                # Chạy tất cả các bài kiểm tra một cách tuần tự
                
                if connections["frontend"]:
                    self.print_header("# filepath: d:\WebDashboard\back\connection_test.py
#!/usr/bin/env python3

import asyncio
import websockets
import json
import time
import socket
import aiohttp
import random
import argparse
import logging
import sys
import signal
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from colorama import init, Fore, Style

# Khởi tạo colorama để hỗ trợ màu trong terminal
init()

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"connection_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger("connection_test")

# Cấu hình mặc định
DEFAULT_CONFIG = {
    "frontend_ws_url": "ws://localhost:9003",
    "tcp_server_host": "localhost",
    "tcp_server_port": 9000,
    "robot_ws_url": "ws://localhost:9002",
    "backend_url": "http://localhost:8000",
    "backend_ws_url": "ws://localhost:8000/ws/robot/",
    "api_key": "140504",
    "robot_id": "test_robot"
}

# Biến toàn cục để theo dõi các kết nối
connections = {
    "frontend": False,
    "tcp": False,
    "robot": False,
    "backend": False
}

# Tạo ID duy nhất cho phiên kiểm tra
SESSION_ID = f"test_{int(time.time())}"

class ConnectionTester:
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG
        self.robot_id = self.config["robot_id"]
        self.frontend_ws = None
        self.robot_ws = None
        self.tcp_socket = None
        self.backend_session = None
        self.backend_ws = None
        self.running = False
        self.test_data = {}
        self.msg_counters = {
            "frontend_sent": 0,
            "frontend_received": 0,
            "tcp_sent": 0,
            "tcp_received": 0,
            "robot_sent": 0,
            "robot_received": 0,
            "backend_sent": 0,
            "backend_received": 0
        }

    def print_header(self, title: str):
        """In header với màu sắc"""
        print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "="*50)
        print(f" {title}")
        print("="*50 + f"{Style.RESET_ALL}\n")

    def print_success(self, message: str):
        """In thông báo thành công với màu xanh lá"""
        print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")

    def print_error(self, message: str):
        """In thông báo lỗi với màu đỏ"""
        print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")

    def print_warning(self, message: str):
        """In thông báo cảnh báo với màu vàng"""
        print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")

    def print_info(self, message: str):
        """In thông tin với màu xanh dương"""
        print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")

    def print_status(self):
        """In trạng thái kết nối hiện tại"""
        print("\n" + "="*30)
        print("TRẠNG THÁI KẾT NỐI:")
        
        for name, status in connections.items():
            status_str = f"{Fore.GREEN}Connected{Style.RESET_ALL}" if status else f"{Fore.RED}Disconnected{Style.RESET_ALL}"
            print(f"  {name.ljust(8)}: {status_str}")
        
        print("="*30)
        print(f"Tin nhắn gửi/nhận:")
        print(f"  Frontend: {self.msg_counters['frontend_sent']} sent, {self.msg_counters['frontend_received']} received")
        print(f"  TCP:      {self.msg_counters['tcp_sent']} sent, {self.msg_counters['tcp_received']} received")
        print(f"  Robot:    {self.msg_counters['robot_sent']} sent, {self.msg_counters['robot_received']} received")
        print(f"  Backend:  {self.msg_counters['backend_sent']} sent, {self.msg_counters['backend_received']} received")
        print("="*30 + "\n")

    async def connect_frontend(self):
        """Kết nối WebSocket giả lập frontend"""
        try:
            self.print_info(f"Đang kết nối đến WebSocket Bridge: {self.config['frontend_ws_url']}")
            self.frontend_ws = await websockets.connect(self.config['frontend_ws_url'])
            connections["frontend"] = True
            self.print_success("Kết nối WebSocket Bridge thành công")
            return True
        except Exception as e:
            self.print_error(f"Lỗi kết nối đến WebSocket Bridge: {e}")
            connections["frontend"] = False
            return False

    async def connect_tcp_server(self):
        """Kết nối trực tiếp đến TCP Server"""
        try:
            self.print_info(f"Đang kết nối đến TCP Server: {self.config['tcp_server_host']}:{self.config['tcp_server_port']}")
            
            # Tạo TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5.0)
            self.tcp_socket.connect((self.config['tcp_server_host'], self.config['tcp_server_port']))
            
            # Đọc welcome message
            welcome_data = self.tcp_socket.recv(4096).decode('utf-8').strip()
            try:
                welcome = json.loads(welcome_data)
                self.print_info(f"TCP Server welcome: {json.dumps(welcome, indent=2)}")
            except:
                self.print_info(f"TCP Server welcome (raw): {welcome_data}")
            
            connections["tcp"] = True
            self.print_success("Kết nối TCP Server thành công")
            return True
        except Exception as e:
            self.print_error(f"Lỗi kết nối đến TCP Server: {e}")
            connections["tcp"] = False
            return False

    async def connect_robot(self):
        """Kết nối WebSocket giả lập robot"""
        try:
            self.print_info(f"Đang kết nối đến WebSocket Robot: {self.config['robot_ws_url']}")
            self.robot_ws = await websockets.connect(self.config['robot_ws_url'])
            
            # Đăng ký robot
            registration = {
                "type": "register",
                "robot_id": self.robot_id,
                "name": f"Test Robot {SESSION_ID}",
                "model": "Test Model",
                "version": "1.0.0",
                "timestamp": time.time()
            }
            
            await self.robot_ws.send(json.dumps(registration))
            self.msg_counters["robot_sent"] += 1
            self.print_info(f"Đã gửi đăng ký robot: {registration}")
            
            # Đợi xác nhận đăng ký
            try:
                response = await asyncio.wait_for(self.robot_ws.recv(), timeout=5.0)
                self.msg_counters["robot_received"] += 1
                response_data = json.loads(response)
                self.print_info(f"Đã nhận xác nhận đăng ký: {response_data}")
            except asyncio.TimeoutError:
                self.print_warning("Không nhận được xác nhận đăng ký (timeout)")
            
            connections["robot"] = True
            self.print_success("Kết nối Robot thành công")
            return True
        except Exception as e:
            self.print_error(f"Lỗi kết nối Robot: {e}")
            connections["robot"] = False
            return False

    async def connect_backend(self):
        """Kiểm tra kết nối đến backend FastAPI"""
        try:
            # Tạo HTTP session
            self.backend_session = aiohttp.ClientSession()
            
            # Kiểm tra health check endpoint
            self.print_info(f"Kiểm tra health check API: {self.config['backend_url']}/api/health-check")
            async with self.backend_session.get(f"{self.config['backend_url']}/api/health-check") as response:
                if response.status == 200:
                    data = await response.json()
                    self.print_success(f"Backend API hoạt động: {data}")
                    connections["backend"] = True
                else:
                    self.print_error(f"Backend API trả về lỗi: {response.status}")
                    connections["backend"] = False
            
            # Kết nối WebSocket đến backend
            self.print_info(f"Đang kết nối đến Backend WebSocket: {self.config['backend_ws_url']}{self.robot_id}")
            headers = {
                "Authorization": f"Bearer {self.config['api_key']}",
                "Origin": self.config['backend_url'],
                "X-Robot-ID": self.robot_id
            }
            
            try:
                self.backend_ws = await websockets.connect(
                    f"{self.config['backend_ws_url']}{self.robot_id}", 
                    extra_headers=headers
                )
                self.print_success("Kết nối Backend WebSocket thành công")
            except Exception as e:
                self.print_error(f"Lỗi kết nối Backend WebSocket: {e}")
            
            return connections["backend"]
        except Exception as e:
            self.print_error(f"Lỗi kết nối đến backend: {e}")
            connections["backend"] = False
            return False
        
    async def test_frontend_to_tcp(self):
        """Kiểm tra gửi dữ liệu từ Frontend đến TCP Server"""
        if not self.frontend_ws:
            self.print_error("Không có kết nối frontend")
            return False
            
        try:
            message = {
                "type": "test_message",
                "robot_id": self.robot_id,
                "data": f"Test từ Frontend {SESSION_ID}",
                "timestamp": time.time()
            }
            
            self.print_info(f"Đang gửi tin nhắn từ Frontend đến TCP Server...")
            start_time = time.time()
            await self.frontend_ws.send(json.dumps(message))
            self.msg_counters["frontend_sent"] += 1
            
            # Đợi phản hồi
            try:
                response = await asyncio.wait_for(self.frontend_ws.recv(), timeout=5.0)
                elapsed = time.time() - start_time
                self.msg_counters["frontend_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ TCP Server qua WebSocket Bridge sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except asyncio.TimeoutError:
                self.print_error("Không nhận được phản hồi từ TCP Server (timeout)")
                return False
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi tin nhắn từ Frontend: {e}")
            return False

    async def test_tcp_to_robot(self):
        """Kiểm tra gửi dữ liệu từ TCP Server đến Robot"""
        if not self.tcp_socket:
            self.print_error("Không có kết nối TCP")
            return False
            
        try:
            # Gửi lệnh từ TCP Server đến Robot
            command = {
                "type": "command",
                "robot_id": self.robot_id,
                "command": "test_command",
                "data": f"Test từ TCP Server {SESSION_ID}",
                "timestamp": time.time()
            }
            
            self.print_info(f"Đang gửi lệnh từ TCP Server đến Robot...")
            start_time = time.time()
            
            # Chuyển thành JSON string và thêm newline
            command_str = json.dumps(command) + '\n'
            self.tcp_socket.sendall(command_str.encode('utf-8'))
            self.msg_counters["tcp_sent"] += 1
            
            # Đọc phản hồi
            try:
                self.tcp_socket.settimeout(5.0)
                response = self.tcp_socket.recv(4096).decode('utf-8').strip()
                elapsed = time.time() - start_time
                self.msg_counters["tcp_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ TCP Server sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except socket.timeout:
                self.print_error("Không nhận được phản hồi từ TCP Server (timeout)")
                return False
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi lệnh từ TCP Server đến Robot: {e}")
            return False

    async def test_robot_to_tcp(self):
        """Kiểm tra gửi dữ liệu từ Robot đến TCP Server"""
        if not self.robot_ws:
            self.print_error("Không có kết nối robot")
            return False
            
        try:
            # Gửi dữ liệu từ Robot đến TCP Server
            data = {
                "type": "sensor_data",
                "robot_id": self.robot_id,
                "data": {
                    "temperature": random.uniform(20, 30),
                    "humidity": random.uniform(40, 60),
                    "battery": random.uniform(70, 100),
                    "session": SESSION_ID
                },
                "timestamp": time.time()
            }
            
            self.print_info(f"Đang gửi dữ liệu từ Robot đến TCP Server...")
            start_time = time.time()
            await self.robot_ws.send(json.dumps(data))
            self.msg_counters["robot_sent"] += 1
            
            # Đợi phản hồi hoặc tin nhắn tiếp theo
            try:
                response = await asyncio.wait_for(self.robot_ws.recv(), timeout=5.0)
                elapsed = time.time() - start_time
                self.msg_counters["robot_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ TCP Server sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except asyncio.TimeoutError:
                self.print_warning("Không nhận được phản hồi từ TCP Server (có thể bình thường)")
                return True  # Vẫn coi là thành công vì robot có thể không nhận được phản hồi
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi dữ liệu từ Robot: {e}")
            return False
    
    async def test_backend_connection(self):
        """Kiểm tra kết nối đến backend FastAPI"""
        if not self.backend_ws:
            self.print_error("Không có kết nối backend WebSocket")
            return False
            
        try:
            # Gửi dữ liệu đến backend
            data = {
                "type": "status_update",
                "robot_id": self.robot_id,
                "status": "testing",
                "data": {
                    "session": SESSION_ID,
                    "timestamp": time.time()
                }
            }
            
            self.print_info(f"Đang gửi dữ liệu đến Backend...")
            start_time = time.time()
            await self.backend_ws.send(json.dumps(data))
            self.msg_counters["backend_sent"] += 1
            
            # Đợi phản hồi
            try:
                response = await asyncio.wait_for(self.backend_ws.recv(), timeout=5.0)
                elapsed = time.time() - start_time
                self.msg_counters["backend_received"] += 1
                
                try:
                    response_data = json.loads(response)
                    self.print_success(f"Đã nhận phản hồi từ Backend sau {elapsed:.4f}s")
                    self.print_info(f"Phản hồi: {json.dumps(response_data, indent=2)}")
                    return True
                except:
                    self.print_warning(f"Đã nhận phản hồi không hợp lệ: {response}")
                    return False
                    
            except asyncio.TimeoutError:
                self.print_warning("Không nhận được phản hồi từ Backend (có thể bình thường)")
                return True
                
        except Exception as e:
            self.print_error(f"Lỗi khi gửi dữ liệu đến Backend: {e}")
            return False

    async def test_full_flow(self):
        """Kiểm tra luồng đầy đủ: Frontend -> TCP -> Robot -> TCP -> Backend"""
        self.print_header("KIỂM TRA LUỒNG ĐẦY ĐỦ")
        
        # Kiểm tra kết nối trước
        if not all([connections["frontend"], connections["tcp"], connections["robot"], connections["backend"]]):
            self.print_warning("Không phải tất cả các kết nối đều đã sẵn sàng. Kết quả có thể không chính xác.")
        
        # Tạo ID duy nhất cho luồng kiểm tra này
        flow_id = f"flow_{int(time.time())}"
        self.print_info(f"Flow ID: {flow_id}")
        
        # Bước 1: Frontend gửi lệnh đến TCP Server
        self.print_info("1. Frontend gửi lệnh đến TCP Server...")
        command = {
            "type": "motor_control",
            "robot_id": self.robot_id,
            "velocities": {
                "x": random.uniform(-1, 1),
                "y": random.uniform(-1, 1),
                "theta": random.uniform(-1, 1)
            },
            "flow_id": flow_id,
            "frontend": True,
            "timestamp": time.time()
        }
        
        try:
            await self.frontend_ws.send(json.dumps(command))
            self.msg_counters["frontend_sent"] += 1
            self.print_success("Đã gửi lệnh từ Frontend")
        except Exception as e:
            self.print_error(f"Lỗi gửi lệnh từ Frontend: {e}")
            return False
            
        # Bước 2: Đợi robot nhận được lệnh từ TCP Server
        self.print_info("2. Đợi Robot nhận lệnh từ TCP Server...")
        
        try:
            received_robot_command = False
            robot_command = None
            
            # Đợi tối đa 10 giây
            start_time = time.time()
            while time.time() - start_time < 10 and not received_robot_command:
                try:
                    message = await asyncio.wait_for(self.robot_ws.recv(), timeout=1.0)
                    self.msg_counters["robot_received"] += 1
                    
                    data = json.loads(message)
                    if data.get("flow_id") == flow_id:
                        received_robot_command = True
                        robot_command = data
                        self.print_success(f"Robot đã nhận lệnh từ TCP Server sau {time.time() - start_time:.2f}s")
                    else:
                        self.print_info("Robot nhận tin nhắn khác (không phải flow hiện tại)")
                        
                except asyncio.TimeoutError:
                    pass
                    
            if not received_robot_command:
                self.print_error("Robot không nhận được lệnh sau 10 giây")
                return False
        except Exception as e:
            self.print_error(f"Lỗi đợi Robot nhận lệnh: {e}")
            return False
            
        # Bước 3: Robot phản hồi trạng thái lên TCP Server
        self.print_info("3. Robot gửi phản hồi đến TCP Server...")
        
        robot_response = {
            "type": "motor_status",
            "robot_id": self.robot_id,
            "status": "executing",
            "original_command": robot_command,
            "flow_id": flow_id,
            "timestamp": time.time()
        }
        
        try:
            await self.robot_ws.send(json.dumps(robot_response))
            self.msg_counters["robot_sent"] += 1
            self.print_success("Robot đã gửi phản hồi đến TCP Server")
        except Exception as e:
            self.print_error(f"Lỗi khi Robot gửi phản hồi: {e}")
            return False
        
        # Bước 4: Đợi frontend nhận phản hồi từ TCP Server
        self.print_info("4. Đợi Frontend nhận phản hồi từ TCP Server...")
        
        try:
            received_frontend_response = False
            frontend_response = None
            
            # Đợi tối đa 10 giây
            start_time = time.time()
            while time.time() - start_time < 10 and not received_frontend_response:
                try:
                    message = await asyncio.wait_for(self.frontend_ws.recv(), timeout=1.0)
                    self.msg_counters["frontend_received"] += 1
                    
                    data = json.loads(message)
                    # Kiểm tra nếu đây là phản hồi cho flow hiện tại
                    if data.get("flow_id") == flow_id or (data.get("original_command") and data.get("original_command").get("flow_id") == flow_id):
                        received_frontend_response = True
                        frontend_response = data
                        self.print_success(f"Frontend đã nhận phản hồi sau {time.time() - start_time:.2f}s")
                    else:
                        self.print_info("Frontend nhận tin nhắn khác (không phải flow hiện tại)")
                        
                except asyncio.TimeoutError:
                    pass
                    
            if not received_frontend_response:
                self.print_warning("Frontend không nhận được phản hồi sau 10 giây")
                # Không return False vì phản hồi có thể không được gửi về frontend
        except Exception as e:
            self.print_error(f"Lỗi đợi Frontend nhận phản hồi: {e}")
        
        # Kiểm tra kết nối backend nếu có
        if connections["backend"] and self.backend_ws:
            # Bước 5: Kiểm tra xem dữ liệu có được chuyển tiếp đến backend không
            self.print_info("5. Kiểm tra Backend nhận dữ liệu...")
            
            try:
                received_backend_data = False
                
                # Đợi tối đa 10 giây
                start_time = time.time()
                while time.time() - start_time < 10 and not received_backend_data:
                    try:
                        message = await asyncio.wait_for(self.backend_ws.recv(), timeout=1.0)
                        self.msg_counters["backend_received"] += 1
                        
                        data = json.loads(message)
                        # Kiểm tra nếu có liên quan đến flow_id
                        if str(data).find(flow_id) != -1:
                            received_backend_data = True
                            self.print_success(f"Backend đã nhận dữ liệu liên quan đến flow sau {time.time() - start_time:.2f}s")
                            self.print_info(f"Dữ liệu: {json.dumps(data, indent=2)}")
                        else:
                            self.print_info("Backend nhận tin nhắn khác (không liên quan đến flow)")
                            
                    except asyncio.TimeoutError:
                        pass
                        
                if not received_backend_data:
                    self.print_warning("Backend không nhận được dữ liệu liên quan sau 10 giây")
            except Exception as e:
                self.print_error(f"Lỗi kiểm tra dữ liệu backend: {e}")
        
        self.print_header("KẾT QUẢ KIỂM TRA LUỒNG")
        self.print_success("Đã hoàn thành kiểm tra luồng dữ liệu")
        self.print_status()
        return True

    async def listen_robot_messages(self):
        """Lắng nghe tin nhắn từ Robot WebSocket"""
        if not self.robot_ws:
            return
            
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.robot_ws.recv(), timeout=1.0)
                    self.msg_counters["robot_received"] += 1
                    data = json.loads(message)
                    
                    # Chỉ log với level debug để tránh spam
                    logger.debug(f"[ROBOT RECV] {data}")
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Lỗi nhận tin nhắn từ Robot: {e}")
                    # Đợi một chút trước khi thử lại
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Lỗi trong listen_robot_messages: {e}")

    async def listen_frontend_messages(self):
        """Lắng nghe tin nhắn từ Frontend WebSocket"""
        if not self.frontend_ws:
            return
            
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.frontend_ws.recv(), timeout=1.0)
                    self.msg_counters["frontend_received"] += 1
                    data = json.loads(message)
                    
                    # Chỉ log với level debug để tránh spam
                    logger.debug(f"[FRONTEND RECV] {data}")
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Lỗi nhận tin nhắn từ Frontend: {e}")
                    # Đợi một chút trước khi thử lại
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Lỗi trong listen_frontend_messages: {e}")

    async def listen_backend_messages(self):
        """Lắng nghe tin nhắn từ Backend WebSocket"""
        if not self.backend_ws:
            return
            
        try:
            while self.running:
                try:
                    message = await asyncio.wait_for(self.backend_ws.recv(), timeout=1.0)
                    self.msg_counters["backend_received"] += 1
                    data = json.loads(message)
                    
                    # Chỉ log với level debug để tránh spam
                    logger.debug(f"[BACKEND RECV] {data}")
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"Lỗi nhận tin nhắn từ Backend: {e}")
                    # Đợi một chút trước khi thử lại
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Lỗi trong listen_backend_messages: {e}")

    async def send_heartbeats(self):
        """Gửi heartbeat định kỳ để giữ kết nối"""
        while self.running:
            try:
                # Gửi heartbeat từ robot
                if self.robot_ws and connections["robot"]:
                    heartbeat = {
                        "type": "heartbeat",
                        "robot_id": self.robot_id,
                        "timestamp": time.time()
                    }
                    await self.robot_ws.send(json.dumps(heartbeat))
                    self.msg_counters["robot_sent"] += 1
                    logger.debug(f"Đã gửi heartbeat từ Robot")
                
                # Đợi 30 giây trước lần gửi tiếp theo
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Lỗi gửi heartbeat: {e}")
                await asyncio.sleep(5)

    async def close_all_connections(self):
        """Đóng tất cả các kết nối"""
        self.running = False
        
        # Đóng robot WebSocket
        if self.robot_ws:
            try:
                await self.robot_ws.close()
                self.print_info("Đã đóng kết nối Robot WebSocket")
            except:
                pass
        
        # Đóng frontend WebSocket
        if self.frontend_ws:
            try:
                await self.frontend_ws.close()
                self.print_info("Đã đóng kết nối Frontend WebSocket")
            except:
                pass
        
        # Đóng backend WebSocket
        if self.backend_ws:
            try:
                await self.backend_ws.close()
                self.print_info("Đã đóng kết nối Backend WebSocket")
            except:
                pass
        
        # Đóng backend HTTP session
        if self.backend_session:
            try:
                await self.backend_session.close()
                self.print_info("Đã đóng kết nối Backend HTTP Session")
            except:
                pass
        
        # Đóng TCP socket
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
                self.print_info("Đã đóng kết nối TCP Socket")
            except:
                pass
        
        # Reset trạng thái kết nối
        for key in connections:
            connections[key] = False

    async def run_test(self, test_type="all"):
        """
        Chạy các bài kiểm tra
        
        Args:
            test_type: Loại kiểm tra cần chạy (all, frontend, tcp, robot, backend, flow)
        """
        self.running = True
        
        # Khởi tạo các task lắng nghe
        tasks = []
        
        try:
            self.print_header("KHỞI TẠO KẾT NỐI")
            
            # Kết nối đến các dịch vụ
            if test_type in ["all", "frontend", "flow"]:
                await self.connect_frontend()
                
            if test_type in ["all", "tcp", "flow"]:
                await self.connect_tcp_server()
                
            if test_type in ["all", "robot", "flow"]:
                await self.connect_robot()
                
            if test_type in ["all", "backend", "flow"]:
                await self.connect_backend()
            
            # Khởi động các task lắng nghe nếu cần thiết cho kiểm tra flow
            if test_type in ["all", "flow", "continuous"]:
                if self.robot_ws:
                    robot_listener = asyncio.create_task(self.listen_robot_messages())
                    tasks.append(robot_listener)
                    
                if self.frontend_ws:
                    frontend_listener =