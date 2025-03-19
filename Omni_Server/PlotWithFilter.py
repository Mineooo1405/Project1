import numpy as np
import matplotlib.pyplot as plt

def apply_filter(signal, b, a):
    """
    Áp dụng bộ lọc thông thấp theo phương trình sai phân (hỗ trợ bậc bất kỳ)
    :param signal: Tín hiệu đầu vào
    :param b: Hệ số tử số (numerator)
    :param a: Hệ số mẫu số (denominator)
    :return: Tín hiệu đã lọc
    """
    order = len(a) - 1  # Bậc của bộ lọc
    y = np.zeros_like(signal)  # Khởi tạo mảng đầu ra

    for n in range(order, len(signal)):
        y[n] = (sum(b[i] * signal[n-i] for i in range(len(b))) -
                sum(a[j] * y[n-j] for j in range(1, len(a)))) / a[0]
    
    return y


b = [0.11216024, 0.11216024]  # Hệ số của x[n], x[n-1], x[n-2]
a = [  1.        , -0.77567951]  # Hệ số của y[n], y[n-1], y[n-2] (a[0] = 1)

# 🛠 In phương trình sai phân
equation = "y[n] = "
equation += " + ".join([f"({b[i]:.6f} * x[n-{i}])" for i in range(len(b))])
equation += " - " + " - ".join([f"({-a[j]:.6f} * y[n-{j}])" for j in range(1, len(a))])
print("Phương trình sai phân:")
print(equation)

# 🛠 Đọc dữ liệu encoder từ file
file_path = "encoder_data.txt"
data = np.loadtxt(file_path)

# Áp dụng bộ lọc cho từng động cơ
filtered_data = np.zeros_like(data)
for i in range(data.shape[1]):  # Duyệt qua từng cột (từng động cơ)
    filtered_data[:, i] = apply_filter(data[:, i], b, a)

# Vẽ kết quả
time = np.arange(len(data)) * 0.02  # Mỗi lần đọc cách nhau 20ms (sampling_freq = 60 Hz)
plt.figure(figsize=(12, 5))
for i in range(data.shape[1]):
    plt.plot(time, data[:, i], linestyle="dotted", label=f'Gốc - Động cơ {i+1}')
    plt.plot(time, filtered_data[:, i], label=f'Lọc - Động cơ {i+1}', linewidth=2)
plt.xlabel("Thời gian (s)")
plt.ylabel("Tốc độ Encoder")
plt.title("So sánh tín hiệu trước và sau khi lọc (Hệ số bộ lọc cập nhật)")
plt.legend()
plt.grid()
plt.show()
