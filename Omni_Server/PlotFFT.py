import numpy as np
import matplotlib.pyplot as plt
from scipy.fftpack import fft, fftfreq

# BƯỚC 1: Đọc dữ liệu từ file .txt
# file_path = "Filter_Data.txt"  # Cập nhật tên file nếu cần
file_path = "Filter_Data.txt"  # Cập nhật tên file nếu cần
data = np.loadtxt(file_path)

# BƯỚC 2: Tách dữ liệu động cơ
rpm_1 = data[:, 0]  # Động cơ 1
rpm_2 = data[:, 1]  # Động cơ 2
rpm_3 = data[:, 2]  # Động cơ 3

# BƯỚC 3: Cài đặt thông số FFT
fs = 50  # Tần số lấy mẫu (Hz)
N = len(rpm_1)  # Số mẫu dữ liệu
T = 1 / fs  # Khoảng thời gian giữa 2 mẫu

# Hàm tính FFT
def compute_fft(signal, N, fs):
    fft_values = fft(signal)  # Thực hiện FFT
    fft_magnitudes = np.abs(fft_values)[:N//2]  # Lấy biên độ nửa đầu phổ tần số
    frequencies = fftfreq(N, d=T)[:N//2]  # Lấy các tần số tương ứng
    return frequencies, fft_magnitudes

# Tính FFT cho từng động cơ
freqs_1, fft_rpm_1 = compute_fft(rpm_1, N, fs)
freqs_2, fft_rpm_2 = compute_fft(rpm_2, N, fs)
freqs_3, fft_rpm_3 = compute_fft(rpm_3, N, fs)

# BƯỚC 4: Vẽ biểu đồ dạng cột
plt.figure(figsize=(12, 5))
plt.bar(freqs_1, fft_rpm_1, width=0.05, alpha=0.6, label="FFT Động cơ 1", color='blue')
plt.bar(freqs_2, fft_rpm_2, width=0.05, alpha=0.6, label="FFT Động cơ 2", color='orange')
plt.bar(freqs_3, fft_rpm_3, width=0.05, alpha=0.6, label="FFT Động cơ 3", color='green')

plt.xlabel("Tần số (Hz)")
plt.ylabel("Biên độ")
plt.title("Phân tích phổ tần số của RPM động cơ (Dạng cột)")
plt.legend()
plt.grid()
plt.show()
