import websocket
import json
import time
import sys

def test_motor_control(robot_id="robot1", motor_speeds=None):
    if motor_speeds is None:
        motor_speeds = [25, 50, 75]  # Default test speeds
    
    # Connect to WebSocket - using the correct method
    ws = websocket.create_connection(f"ws://localhost:8000/ws/{robot_id}")
    
    # Wait for welcome message
    welcome = json.loads(ws.recv())
    print(f"Connected: {welcome}")
    
    # Send motor control command
    command = {
        "type": "motor_control",
        "speeds": motor_speeds,
        "robot_id": robot_id
    }
    
    print(f"Sending motor control command: {command}")
    ws.send(json.dumps(command))
    
    # Wait for response
    response = json.loads(ws.recv())
    print(f"Received response: {response}")
    
    # Close connection
    ws.close()
    print("Connection closed")

if __name__ == "__main__":
    robot_id = sys.argv[1] if len(sys.argv) > 1 else "robot1"
    speeds = [int(s) for s in sys.argv[2:5]] if len(sys.argv) > 4 else [10, 20, 30]
    
    test_motor_control(robot_id, speeds)