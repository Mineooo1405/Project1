import socket
import json
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Tắt buffering TCP
sock.connect(("127.0.0.1", 5005))

# Nhận phản hồi từ server khi yêu cầu ID
response = sock.recv(1024).decode().strip()
print(f"Received from server: {response}")

# Gửi ID robot
sock.sendall(b"robot1\n")
time.sleep(1)

# Gửi nhiều gói dữ liệu mà không đóng socket
for i in range(5):
    data = {"yaw": 0.5 + i * 0.1, "omega": [73.94, 70.3, 71.52], "dt": 0.1}
    msg = json.dumps(data) + "\n"
    
    sock.sendall(msg.encode())  # Gửi dữ liệu mà không shutdown
    print(f"Sent data {i + 1}: {data}")
    
    try:
        response = sock.recv(1024).decode().strip()
        print(f"Received from server: {response}")
    except socket.error:
        print("Error receiving server response")
    
    time.sleep(2)

# Giữ kết nối mở thêm 10 giây để kiểm tra server có đóng không
print("Keeping connection open for 10 seconds...")
time.sleep(10)

sock.close()
print("Closed connection.")
