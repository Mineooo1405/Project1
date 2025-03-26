import asyncio
import websockets
import socket
import json
import time
import logging
import threading
import os

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("direct_bridge")

# Global variables
tcp_clients = {}  # robot_id -> socket
ws_clients = {}   # client_id -> websocket

# Đọc cấu hình port từ biến môi trường hoặc sử dụng mặc định
TCP_PORT = int(os.environ.get("TCP_PORT", "9000"))
WS_PORT = int(os.environ.get("WS_BRIDGE_PORT", "9003"))

class DirectBridge:
    def __init__(self, tcp_port=TCP_PORT, ws_port=WS_PORT):
        self.tcp_port = tcp_port
        self.ws_port = ws_port
        self.tcp_server = None
        self.ws_server = None
        self.running = False
    
    async def start(self):
        """Start both TCP and WebSocket servers"""
        self.running = True
        
        # Start TCP server - Sửa 'localhost' thành '0.0.0.0'
        self.tcp_server = await asyncio.start_server(
            self.handle_tcp_client, '0.0.0.0', self.tcp_port
        )
        logger.info(f"TCP server started on 0.0.0.0:{self.tcp_port}")
        
        # Start WebSocket server - Sửa cả WebSocket nữa
        self.ws_server = await websockets.serve(
            self.handle_ws_client, '0.0.0.0', self.ws_port
        )
        logger.info(f"WebSocket server started on 0.0.0.0:{self.ws_port}")
        
        # Keep servers running
        await asyncio.gather(
            self.tcp_server.serve_forever(),
            self.ws_server.wait_closed()
        )
    
    async def handle_tcp_client(self, reader, writer):
        """Handle TCP client connection (robot)"""
        addr = writer.get_extra_info('peername')
        client_id = f"{addr[0]}:{addr[1]}"
        robot_id = None
        logger.info(f"TCP client connected: {client_id}")
        
        # Send welcome message
        welcome = {
            "type": "welcome",
            "message": "Connected to TCP server",
            "timestamp": time.time()
        }
        writer.write((json.dumps(welcome) + "\n").encode())
        await writer.drain()
        
        buffer = ""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                
                buffer += data.decode()
                
                # Process complete messages
                while "\n" in buffer:
                    message, buffer = buffer.split("\n", 1)
                    if not message.strip():
                        continue
                    
                    try:
                        # Parse JSON
                        msg = json.loads(message)
                        msg_type = msg.get("type", "unknown")
                        
                        # Handle registration
                        if msg_type == "registration":
                            robot_id = msg.get("robot_id", "unknown")
                            logger.info(f"Robot registered: {robot_id}")
                            tcp_clients[robot_id] = writer
                            
                            # Send confirmation
                            response = {
                                "type": "registration_confirmation",
                                "robot_id": robot_id,
                                "status": "success",
                                "timestamp": time.time()
                            }
                            writer.write((json.dumps(response) + "\n").encode())
                            await writer.drain()
                        
                        # Forward other messages to WebSocket clients
                        elif robot_id:
                            logger.info(f"Forwarding from robot {robot_id} to all WebSocket clients: {msg_type}")
                            
                            # Send to all WebSocket clients
                            for ws in ws_clients.values():
                                try:
                                    await ws.send(json.dumps(msg))
                                except:
                                    pass
                            
                            # Send acknowledgment
                            response = {
                                "type": "data_ack",
                                "status": "received",
                                "message_type": msg_type,
                                "timestamp": time.time()
                            }
                            writer.write((json.dumps(response) + "\n").encode())
                            await writer.drain()
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON from TCP client: {message}")
                    except Exception as e:
                        logger.error(f"Error processing TCP message: {e}")
        except Exception as e:
            logger.error(f"TCP client error: {e}")
        finally:
            # Clean up
            if robot_id and robot_id in tcp_clients:
                del tcp_clients[robot_id]
            writer.close()
            await writer.wait_closed()
            logger.info(f"TCP client disconnected: {client_id}")
    
    async def handle_ws_client(self, websocket, path):
        """Handle WebSocket client connection (frontend)"""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"WebSocket client connected: {client_id}")
        
        # Add to clients
        ws_clients[client_id] = websocket
        
        # Send welcome
        await websocket.send(json.dumps({
            "type": "heartbeat",
            "robot_id": "websocket_bridge",
            "source": "ws_bridge",
            "timestamp": time.time()
        }))
        
        try:
            async for message in websocket:
                try:
                    # Parse message
                    msg = json.loads(message)
                    msg_type = msg.get("type", "unknown")
                    robot_id = msg.get("robot_id", "unknown")
                    
                    logger.info(f"Received from WebSocket client {client_id}: {msg_type} for robot {robot_id}")
                    
                    # Add frontend flag
                    if "frontend" not in msg:
                        msg["frontend"] = True
                    
                    # Forward to robot
                    if robot_id in tcp_clients:
                        # Get robot writer
                        robot_writer = tcp_clients[robot_id]
                        
                        # Forward message
                        try:
                            robot_writer.write((json.dumps(msg) + "\n").encode())
                            await robot_writer.drain()
                            logger.info(f"Forwarded to robot {robot_id}: {msg_type}")
                            
                            # Send acknowledgment
                            await websocket.send(json.dumps({
                                "type": "command_sent",
                                "status": "success",
                                "robot_id": robot_id,
                                "timestamp": time.time()
                            }))
                        except Exception as e:
                            logger.error(f"Error forwarding to robot {robot_id}: {e}")
                            await websocket.send(json.dumps({
                                "type": "error",
                                "status": "forward_failed",
                                "message": f"Error forwarding to robot: {str(e)}",
                                "timestamp": time.time()
                            }))
                    else:
                        # Robot not found
                        logger.warning(f"Robot not found: {robot_id}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "status": "not_found",
                            "message": f"Robot {robot_id} not connected",
                            "timestamp": time.time()
                        }))
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from WebSocket client: {message}")
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"WebSocket client error: {e}")
        finally:
            # Clean up
            if client_id in ws_clients:
                del ws_clients[client_id]

# Main function
async def main():
    bridge = DirectBridge()
    await bridge.start()

if __name__ == "__main__":
    print("Starting Direct Bridge - combines TCP server and WebSocket server in one process")
    print("Use localhost:9000 for robots (TCP)")
    print("Use ws://localhost:9003 for frontend (WebSocket)")
    print("-" * 50)
    asyncio.run(main())