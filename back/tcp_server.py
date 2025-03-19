import socket
import json
import threading
import datetime
import logging
import time
import sys
import os
import traceback

# Add parent directory to path to import database modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from back.database import SessionLocal, IMUData, EncoderData, MotorControl, TrajectoryData, PIDConfig

# Import the text function to properly handle SQL queries
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tcp_server.log")
    ]
)
logger = logging.getLogger("tcp_server")

# Global variables
HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 9000      # Port to listen on
BUFFER_SIZE = 4096
active_connections = []

def handle_client(client_socket, addr):
    """Handle a client connection with enhanced logging"""
    client_id = f"{addr[0]}:{addr[1]}"
    logger.info(f"=== NEW CLIENT CONNECTION FROM {client_id} ===")
    active_connections.append(client_id)
    logger.info(f"New connection from {client_id}. Total connections: {len(active_connections)}")
    
    # Send welcome message
    welcome_msg = json.dumps({
        "type": "welcome",
        "message": "Connected to Robot Data TCP Server",
        "server_time": datetime.now().isoformat(),
        "client_id": len(active_connections)
    })
    client_socket.sendall(welcome_msg.encode() + b'\n')
    logger.info(f"Welcome message sent to {client_id}")
    
    try:
        buffer = ""
        while True:
            # Log waiting for data
            logger.debug(f"Waiting for data from {client_id}...")
            
            # Receive data
            data = client_socket.recv(1024)
            if not data:
                logger.info(f"Client {client_id} closed connection (no more data)")
                break
                
            # Log raw received data
            logger.debug(f"Raw data received from {client_id}: {data}")
            
            # Process received data
            buffer += data.decode('utf-8')
            logger.debug(f"Current buffer for {client_id}: {buffer}")
            
            # Process complete messages (each ending with newline)
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                
                # Log the received message with clear separation
                logger.info(f"=== RECEIVED MESSAGE from {client_id} ===")
                logger.info(f"Message: {line}")
                
                try:
                    # Parse JSON
                    logger.debug(f"Parsing JSON from {client_id}...")
                    message = json.loads(line)
                    
                    # Log structured message
                    logger.info(f"Parsed JSON: {json.dumps(message, indent=2)}")
                    message_type = message.get('type')
                    logger.info(f"Message type: {message_type}")
                    
                    # Process motor control command
                    if message_type == 'motor_control':
                        speeds = message.get('speeds', [0, 0, 0])
                        robot_id = message.get('robot_id', 'unknown')
                        
                        logger.info(f"=== INCOMING MOTOR CONTROL REQUEST ===")
                        logger.info(f"From client: {client_id}")
                        logger.info(f"For robot: {robot_id}")
                        logger.info(f"Speed values: {speeds}")
                        
                        # Store in database
                        try:
                            db = SessionLocal()
                            
                            # Create motor control record
                            motor_control = MotorControl(
                                robot_id=robot_id,
                                speeds=speeds,
                                timestamp=datetime.now()
                            )
                            
                            db.add(motor_control)
                            db.commit()
                            logger.info(f"Motor control command stored in database with ID: {motor_control.id}")
                            
                        except Exception as db_err:
                            logger.error(f"Database error: {str(db_err)}")
                        finally:
                            db.close()
                        
                        # Log what would happen next in real implementation
                        logger.info(f"=== SENDING TO ROBOT {robot_id} ===")
                        logger.info(f"Motor 1 speed: {speeds[0] if len(speeds) > 0 else 0}")
                        logger.info(f"Motor 2 speed: {speeds[1] if len(speeds) > 1 else 0}")
                        logger.info(f"Motor 3 speed: {speeds[2] if len(speeds) > 2 else 0}")
                        
                        # Simulate sending to robot with delay
                        logger.info("Transmitting command to robot...")
                        time.sleep(0.1)  # Simulate brief communication delay
                        logger.info("Command sent to robot successfully")
                        
                        # Create response
                        response = {
                            "type": "motor_response",
                            "status": "success", 
                            "message": f"Motor speeds set to {speeds}",
                            "robot_id": robot_id,
                            "timestamp": time.time()
                        }
                        
                        # Log response
                        logger.info(f"=== SENDING RESPONSE to {client_id} ===")
                        logger.info(f"Response: {json.dumps(response, indent=2)}")
                        
                        # Send response
                        response_data = json.dumps(response) + '\n'
                        client_socket.sendall(response_data.encode())
                        logger.info(f"Response sent ({len(response_data)} bytes)")
                        
                    else:
                        logger.warning(f"Unknown message type: {message_type}")
                        
                        # Send error response
                        error_response = {
                            "type": "error",
                            "status": "error",
                            "message": f"Unsupported message type: {message_type}",
                            "timestamp": time.time()
                        }
                        client_socket.sendall((json.dumps(error_response) + '\n').encode())
                        logger.info(f"Error response sent for unsupported type: {message_type}")
                        
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from {client_id}: {line}")
                    # Send error response
                    error_response = {
                        "type": "error",
                        "status": "error",
                        "message": "Invalid JSON format",
                        "timestamp": time.time()
                    }
                    client_socket.sendall((json.dumps(error_response) + '\n').encode())
                    
                except Exception as process_error:
                    logger.error(f"Error processing message: {str(process_error)}")
                    logger.error(traceback.format_exc())
                    
                    # Send error response
                    error_response = {
                        "type": "error",
                        "status": "error",
                        "message": f"Internal server error: {str(process_error)}",
                        "timestamp": time.time()
                    }
                    client_socket.sendall((json.dumps(error_response) + '\n').encode())
                
                # Log end of message processing
                logger.info(f"=== END PROCESSING MESSAGE from {client_id} ===\n")
                    
    except ConnectionResetError:
        logger.warning(f"Connection reset by {client_id}")
    except BrokenPipeError:
        logger.warning(f"Broken pipe with {client_id}")
    except Exception as e:
        logger.error(f"Error handling client {addr}: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        client_socket.close()
        logger.info(f"Connection from {addr} closed")
        if client_id in active_connections:
            active_connections.remove(client_id)
        logger.info(f"Connection closed for {client_id}. Remaining connections: {len(active_connections)}")

# Update the process_data function to handle all data types
def process_data(data):
    """Process received JSON data and store in database"""
    if not isinstance(data, dict):
        return {"status": "error", "message": "Data must be a JSON object"}
    
    # Extract data type and robot ID
    data_type = data.get("type")
    robot_id = data.get("robot_id", "unknown")
    timestamp = datetime.now()
    
    if not data_type:
        return {"status": "error", "message": "Missing 'type' field"}
    
    # Create database session
    try:
        db = SessionLocal()
        logger.debug(f"Database session created for {data_type}")
        
        # Process based on data type
        if data_type == "imu_data":
            # Extract IMU data
            orientation = data.get("orientation", {})
            acceleration = data.get("acceleration", {})
            angular_velocity = data.get("angular_velocity", {})
            
            logger.debug(f"Creating IMU record for robot {robot_id}")
            
            # Create new IMU data record
            imu_data = IMUData(
                robot_id=robot_id,
                accel_x=acceleration.get("x", 0),
                accel_y=acceleration.get("y", 0),
                accel_z=acceleration.get("z", 0),
                gyro_x=angular_velocity.get("x", 0),
                gyro_y=angular_velocity.get("y", 0),
                gyro_z=angular_velocity.get("z", 0),
                timestamp=timestamp,
                raw_data=data
            )
            
            db.add(imu_data)
            db.commit()
            logger.info(f"Stored IMU data for robot {robot_id}")
            return {
                "status": "success",
                "message": "IMU data stored successfully",
                "record_id": imu_data.id
            }
            
        elif data_type == "encoder_data":
            # Extract encoder data - only RPM is needed now
            rpm = data.get("rpm", [0, 0, 0])
            
            # Create new encoder data record
            encoder_data = EncoderData(
                robot_id=robot_id,
                rpm=rpm,
                timestamp=timestamp,
                raw_data=data
            )
            
            db.add(encoder_data)
            db.commit()
            logger.info(f"Stored encoder data for robot {robot_id}")
            return {
                "status": "success",
                "message": "Encoder data stored successfully",
                "record_id": encoder_data.id
            }
            
        elif data_type == "trajectory_data":
            # Extract trajectory data
            current_x = data.get("current_x", 0)
            current_y = data.get("current_y", 0)
            current_theta = data.get("current_theta", 0)
            # Target position fields removed
            status = data.get("status", "idle")
            progress_percent = data.get("progress_percent", 0)
            points = data.get("points", {})
            
            logger.debug(f"Creating trajectory record for robot {robot_id}")
            
            # Create new trajectory data record
            trajectory_data = TrajectoryData(
                robot_id=robot_id,
                current_x=current_x,
                current_y=current_y,
                current_theta=current_theta,
                # Target fields removed
                status=status,
                progress_percent=progress_percent,
                points=points,
                timestamp=timestamp,
                raw_data=data
            )
            
            db.add(trajectory_data)
            db.commit()
            logger.info(f"Stored trajectory data for robot {robot_id}")
            return {
                "status": "success",
                "message": "Trajectory data stored successfully",
                "record_id": trajectory_data.id
            }
            
        elif data_type == "pid_config":
            # Extract PID configuration data
            motor_id = data.get("motor_id", 1)
            kp = data.get("kp", 0)
            ki = data.get("ki", 0)
            kd = data.get("kd", 0)
            
            logger.debug(f"Creating PID config record for robot {robot_id}, motor {motor_id}")
            
            # Create new PID config record
            pid_config = PIDConfig(
                robot_id=robot_id,
                motor_id=motor_id,
                kp=kp,
                ki=ki,
                kd=kd,
                timestamp=timestamp,
                raw_data=data
            )
            
            db.add(pid_config)
            db.commit()
            logger.info(f"Stored PID configuration for robot {robot_id}, motor {motor_id}")
            return {
                "status": "success",
                "message": "PID configuration stored successfully",
                "record_id": pid_config.id
            }
            
        else:
            logger.warning(f"Unknown data type received: {data_type}")
            return {"status": "error", "message": f"Unknown data type: {data_type}"}
            
    except Exception as e:
        logger.error(f"Database error processing {data_type} for {robot_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": f"Database error: {str(e)}"}
    finally:
        db.close()

def start_server():
    """Start the TCP server"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen(5)
        logger.info(f"TCP Server started on {HOST}:{PORT}")
        
        while True:
            client_sock, address = server.accept()
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_sock, address)
            )
            client_thread.daemon = True
            client_thread.start()
    
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        server.close()

if __name__ == "__main__":
    start_server()