import os
import sys
import subprocess

# Thiết lập biến môi trường chính xác (không có khoảng trắng)
os.environ["LOG_LEVEL"] = "INFO"
os.environ["LOG_HEARTBEATS"] = "0"
os.environ["LOG_DETAILED_MESSAGES"] = "1"
os.environ["DEBUG_MODE"] = "1"

# Chạy TCP server
subprocess.run([sys.executable, "tcp_server.py"])