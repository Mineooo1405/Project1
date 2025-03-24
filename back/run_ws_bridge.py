import os
import sys
import subprocess
import socket

# Kiểm tra xem port 9002 đã có ai sử dụng chưa
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

# Thiết lập biến môi trường chính xác (không có khoảng trắng)
os.environ["LOG_LEVEL"] = "INFO"
os.environ["LOG_HEARTBEATS"] = "0"
os.environ["LOG_DETAILED_MESSAGES"] = "1"
os.environ["DEBUG_MODE"] = "1"
os.environ["WS_BRIDGE_PORT"] = "9002"

# Kiểm tra port
if is_port_in_use(9002):
    print("CẢNH BÁO: Port 9002 đã được sử dụng. Không thể khởi động WebSocket Bridge.")
    print("Vui lòng đóng tất cả các ứng dụng đang sử dụng port 9002 hoặc khởi động lại máy tính.")
    sys.exit(1)

# Chạy WebSocket Bridge
subprocess.run([sys.executable, "ws_tcp_bridge.py"])