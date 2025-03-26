import socket
import json
import time
import sys
import traceback

def test_tcp_connection(host='localhost', port=9000):
    """Kiểm tra kết nối TCP đến server và gửi tin nhắn test"""
    print(f"========= TEST TCP CONNECTION ==========")
    print(f"Đang kiểm tra kết nối đến {host}:{port}...")
    
    try:
        # Tạo socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)  # 5 giây timeout
        
        # Kết nối
        print(f"Đang kết nối...")
        start_time = time.time()
        sock.connect((host, port))
        connect_time = time.time() - start_time
        print(f"Đã kết nối thành công! (Thời gian: {connect_time:.4f}s)")
        
        # Đọc welcome message
        print("Đợi welcome message...")
        try:
            start_time = time.time()
            data = sock.recv(4096)
            recv_time = time.time() - start_time
            if data:
                message = data.decode('utf-8').strip()
                print(f"Đã nhận welcome ({recv_time:.4f}s): {message}")
            else:
                print(f"Không nhận được welcome message sau {recv_time:.4f}s")
        except socket.timeout:
            print("Đã hết thời gian chờ welcome message (timeout)")
        
        # Gửi test message
        test_message = {
            "type": "test_message",
            "robot_id": "test_robot",
            "message": "Hello from test script",
            "timestamp": time.time()
        }
        
        print(f"\nĐang gửi tin nhắn test...")
        message_str = json.dumps(test_message) + '\n'
        start_time = time.time()
        sock.sendall(message_str.encode('utf-8'))
        send_time = time.time() - start_time
        print(f"Đã gửi tin nhắn ({send_time:.4f}s): {message_str.strip()}")
        
        # Đọc phản hồi
        print("\nĐợi phản hồi...")
        try:
            start_time = time.time()
            sock.settimeout(5.0)
            response = sock.recv(4096)
            resp_time = time.time() - start_time
            
            if response:
                response_str = response.decode('utf-8').strip()
                print(f"Đã nhận phản hồi ({resp_time:.4f}s): {response_str}")
            else:
                print(f"Không có phản hồi sau {resp_time:.4f}s")
        except socket.timeout:
            print("Đã hết thời gian chờ phản hồi (timeout)")
        
        # Đóng kết nối
        sock.close()
        print("\nKết nối đã đóng")
        print("======= TEST HOÀN THÀNH =======")
        return True
    except ConnectionRefusedError:
        print(f"LỖI: Kết nối bị từ chối. TCP Server có thể không chạy trên {host}:{port}")
        return False
    except Exception as e:
        print(f"LỖI: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    host = 'localhost'
    port = 9000
    
    # Cho phép truyền host và port qua command line
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    # Thực hiện kiểm tra
    test_tcp_connection(host, port)