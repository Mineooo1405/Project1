import numpy as np
import matplotlib.pyplot as plt

# Thông số robot
wheel_radius = 0.03
robot_radius = 0.153
dt = 0.05

# Load dữ liệu
data = np.loadtxt("encoder_data.txt")
rpm_data = np.array(data)
omega_wheel = rpm_data * (2 * np.pi / 60)

# Khởi tạo vị trí
x, y, theta = 0, 0, 0
x_hist, y_hist = [x], [y]

# Hàm động học
def compute_velocity(theta, omega):
    H = np.array([
        [-np.sin(theta), np.cos(theta), robot_radius],
        [-np.sin(np.pi / 3 - theta), -np.cos(np.pi / 3 - theta), robot_radius],
        [np.sin(np.pi / 3 + theta), -np.cos(np.pi / 3 + theta), robot_radius]
    ])
    omega_scaled = omega * wheel_radius
    velocities = np.linalg.solve(H, omega_scaled)
    return velocities[0], velocities[1], velocities[3]

# Tính toán vị trí
for omega in omega_wheel:
    v_x, v_y, _ = compute_velocity(theta, omega)
    x += v_x * dt
    y += v_y * dt
    x_hist.append(x)
    y_hist.append(y)

# Đổi từ mét sang cm để dễ nhìn
x_hist_cm = np.array(x_hist) * 100
y_hist_cm = np.array(y_hist) * 100

# Tạo figure lớn và dễ nhìn
plt.figure(figsize=(12, 8))  # Kích thước figure lớn hơn

# Plot dữ liệu
plt.plot(x_hist_cm, y_hist_cm, marker='o', linewidth=2)

# Đặt tên và đơn vị cho trục
plt.xlabel("X (cm)", fontsize=14)
plt.ylabel("Y (cm)", fontsize=14)
plt.title("Quỹ đạo robot Omni 3 bánh (đơn vị cm)", fontsize=16)

# Thêm lưới
plt.grid(True)

# Đảm bảo tỷ lệ trục x, y bằng nhau
plt.axis("equal")

# Hiển thị plot
plt.show()
