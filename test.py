import requests

API_URL = "http://localhost:8000/trajectory/"  # API lấy dữ liệu quỹ đạo
DATA = {
    "x_position": 1.5,
    "y_position": 2.3,
    "angel": 0.785,  # 45 độ (rad)
}

# Gửi dữ liệu giả lên database qua TCP
response = requests.post("http://localhost:8000/trajectory/", json=DATA)
print("📡 Phản hồi từ server:", response.json())
