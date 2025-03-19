import os
import json
import socket
import threading
import re
import time
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from raw_control import ControlGUI

from rpm_plot import update_rpm_plot
from rpm_plot import rpm_plotter


class Server:
    def __init__(self, gui):
        self.gui = gui
        
        self.control_active = False
        self.firmware_active = False
        self.file_path = None
        self.speed = [0, 0, 0]  # Speed for three motors
        self.encoders = [0, 0, 0]  # Encoder values for three motors
        self.pid_values = [[0.0, 0.0, 0.0] for _ in range(3)]  # PID values as floats
        self.server_socket = None
        self.client_socket = None
        self.sending_firmware = False
        self.client_connected = False
        self.connection_status = "Disconnected"
        self.log_data = True  # Enable data logging by default
                # Khởi tạo dictionary để quản lý file log
        self.log_files = {}
        self.start_times = {}
        self.supported_types = ["encoder", "bno055", "log"]
    
        # Tạo file log mới cho loại dữ liệu
    def setup_log_file(self, data_type):
        if not self.log_data or data_type in self.log_files:
            return
            
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_filename = f"{log_dir}/{data_type}_log_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        
        self.log_files[data_type] = open(log_filename, "w")
        
        # Tạo header dựa vào loại dữ liệu
        if data_type == "encoder":
            self.log_files[data_type].write("Time RPM1 RPM2 RPM3\n")
        elif data_type == "bno055":
            self.log_files[data_type].write("Time Heading Pitch Roll AccelX AccelY AccelZ GravityX GravityY GravityZ\n")
        elif data_type == "log":
            self.log_files[data_type].write("Time Message\n")
            
        self.start_times[data_type] = time.time()
        self.gui.update_monitor(f"Started logging {data_type} data to {log_filename}")
    
    # Đóng tất cả file log
    def close_all_logs(self):
        for log_type, log_file in self.log_files.items():
            log_file.close()
            self.gui.update_monitor(f"{log_type.capitalize()} data log closed")
        self.log_files = {}
        self.start_times = {}

    def start_firmware_server(self):
        if self.firmware_active:
            self.gui.update_monitor("Firmware server already running.")
            return
        
        self.firmware_active = True
        threading.Thread(target=self.firmware_server_thread, daemon=True).start()

    def firmware_server_thread(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", 12345))
            self.server_socket.listen(1)
            self.gui.update_monitor("Firmware server started, waiting for client...")
            self.gui.update_status("Firmware server listening")
            
            self.client_socket, addr = self.server_socket.accept()
            self.client_connected = True
            self.connection_status = f"Connected to {addr[0]}:{addr[1]}"
            self.gui.update_monitor(f"Client connected for firmware: {addr}")
            self.gui.update_status(self.connection_status)
            self.gui.enable_file_selection()

            threading.Thread(target=self.receive_upgrade, args=(self.client_socket,), daemon=True).start()
            
            # Send initialization message to client
            # init_message = "WAIT_FOR_FIRMWARE"
            # self.client_socket.sendall(init_message.encode())
            # self.gui.update_monitor("Sent initialization message to client")
            
        except Exception as e:
            self.firmware_active = False
            self.gui.update_monitor(f"Error starting firmware server: {e}")
            self.gui.update_status("Server error")

    def send_firmware(self):
        if not self.client_connected:
            self.gui.update_monitor("No client connected.")
            messagebox.showerror("Error", "No client connected")
            return
            
        if not self.file_path:
            self.gui.update_monitor("No firmware file selected.")
            messagebox.showerror("Error", "Please select a firmware file first")
            return
            
        try:
            self.sending_firmware = True
            self.gui.update_status("Sending firmware...")
            file_size = 0
            sent_bytes = 0
            
            with open(self.file_path, "rb") as f:
                # Get file size
                f.seek(0, 2)
                file_size = f.tell()
                f.seek(0)
                
                # Send in chunks
                chunk_size = 1024
                self.gui.setup_progress_bar(file_size)
                
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.client_socket.sendall(chunk)
                    sent_bytes += len(chunk)
                    self.gui.update_progress(sent_bytes)
                    
            self.gui.update_monitor(f"Firmware sent successfully: {sent_bytes} bytes")
            messagebox.showinfo("Success", "Firmware sent successfully")
        except Exception as e:
            self.gui.update_monitor(f"Error sending firmware: {e}")
            messagebox.showerror("Error", f"Failed to send firmware: {e}")
        finally: 
            self.sending_firmware = False
            self.gui.hide_progress_bar()
            self.gui.update_status(self.connection_status)
            self.client_socket.shutdown(socket.SHUT_WR)
    
    def receive_upgrade(self, sock):
        try:
            while True:
                if self.sending_firmware:
                    time.sleep(0.1)
                    continue

                data = sock.recv(1024).decode()
                if not data:
                    self.gui.update_monitor("Firmware client disconnected")
                    break
                self.gui.update_monitor(f"Upgrade status: {data}")
        except Exception as e:
            self.gui.update_monitor(f"Error receiving upgrade status: {e}")
        finally:
            # Đóng socket khi client ngắt kết nối
            try:
                if sock:
                    sock.close()
            except:
                pass
            if self.client_socket == sock:
                self.client_socket = None
            self.client_connected = False
            self.connection_status = "Disconnected"
            self.gui.update_status("Disconnected")
            self.gui.disable_buttons()

    def send_upgrade_command(self):
        if not self.client_connected:
            messagebox.showerror("Error", "No client connected")
            return
            
        try:
            self.client_socket.sendall(b"Upgrade")
            self.gui.update_monitor("Sent 'Upgrade' command to the client.")
        except Exception as e:
            self.gui.update_monitor(f"Failed to send 'Upgrade' command: {e}")

    def start_control_server(self):
        if self.control_active:
            self.gui.update_monitor("Control server already running.")
            return
            
        self.control_active = True
        threading.Thread(target=self.control_server_thread, daemon=True).start()

    def stop_control_server(self):
        if not self.control_active:
            return
            
        self.control_active = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            
        self.gui.update_monitor("Control server stopped")
        self.gui.update_status("Server stopped")

    def control_server_thread(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", 12346))
            self.server_socket.listen(1)
            self.control_active = True
            self.gui.update_status("Waiting for connection...")
            
            while self.control_active:
                try:
                    self.client_socket, addr = self.server_socket.accept()
                    self.client_socket.settimeout(0.5)
                    self.client_connected = True
                    self.gui.update_status(f"Connected to {addr[0]}")
                    self.gui.enable_control_buttons()
                    
                    # Gọi hàm mới thay vì hàm cũ
                    self.receive_client_data(self.client_socket)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    self.gui.update_monitor(f"Server error: {e}")
                    break
                    
        except Exception as e:
            self.gui.update_monitor(f"Server init error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
            self.control_active = False
            self.gui.update_status("Server stopped")
            self.gui.disable_buttons()

        # Hàm xử lý dữ liệu encoder
    def process_encoder_data(self, encoder_data):
        if not isinstance(encoder_data, list) or len(encoder_data) < 3:
            self.gui.update_monitor(f"Invalid encoder data format: {encoder_data}")
            return
            
        # Cập nhật giá trị encoder
        self.encoders[0] = float(encoder_data[0])
        self.encoders[1] = float(encoder_data[1])
        self.encoders[2] = float(encoder_data[2])
        
        # Cập nhật UI
        self.gui.update_encoders(self.encoders)
        update_rpm_plot(self.encoders)
        
        # Ghi log nếu được bật
        self.setup_log_file("encoder")
        if self.log_data and "encoder" in self.log_files:
            timestamp = time.time() - self.start_times["encoder"]
            self.log_files["encoder"].write(f"{timestamp:.3f} {' '.join([str(e) for e in self.encoders])}\n")
            self.log_files["encoder"].flush()

    # Hàm xử lý dữ liệu BNO055
    def process_bno055_data(self, bno_data):
        """
        Xử lý dữ liệu BNO055 theo định dạng mới
        
        Format dữ liệu:
        {
            "time": thời_gian,
            "euler": [heading, pitch, roll],
            "lin_accel": [x, y, z],
            "gravity": [x, y, z]
        }
        """
        try:
            # Kiểm tra xem bno_data có phải dict không
            if not isinstance(bno_data, dict):
                self.gui.update_monitor(f"Invalid BNO055 data format, expected dictionary")
                return

            # Lấy dữ liệu từ JSON
            time_val = bno_data.get("time", 0)
            euler = bno_data.get("euler", [0, 0, 0])
            lin_accel = bno_data.get("lin_accel", [0, 0, 0])
            gravity = bno_data.get("gravity", [0, 0, 0])

            # Kiểm tra dữ liệu có đủ không
            if len(euler) < 3 or len(lin_accel) < 3 or len(gravity) < 3:
                self.gui.update_monitor(f"Incomplete BNO055 data")
                return

            # Giải nén dữ liệu euler
            heading, pitch, roll = euler[0], euler[1], euler[2]
            
            # Giải nén dữ liệu gia tốc
            accel_x, accel_y, accel_z = lin_accel[0], lin_accel[1], lin_accel[2]
            
            # Giải nén dữ liệu trọng lực
            gravity_x, gravity_y, gravity_z = gravity[0], gravity[1], gravity[2]
            
            # # Hiển thị thông tin quan trọng lên UI
            # self.gui.update_monitor(
            #     f"BNO055: Heading={heading:.2f}° Pitch={pitch:.2f}° Roll={roll:.2f}° | "
            #     f"Accel: [{accel_x:.2f}, {accel_y:.2f}, {accel_z:.2f}] m/s²"
            # )
            
            # Ghi log nếu được bật
            self.setup_log_file("bno055")
            if self.log_data and "bno055" in self.log_files:
                # Lưu đầy đủ dữ liệu
                self.log_files["bno055"].write(
                    f"{time_val:.3f} {heading:.2f} {pitch:.2f} {roll:.2f} "
                    f"{accel_x:.2f} {accel_y:.2f} {accel_z:.2f} "
                    f"{gravity_x:.2f} {gravity_y:.2f} {gravity_z:.2f}\n"
                )
                self.log_files["bno055"].flush()
                
        except Exception as e:
            self.gui.update_monitor(f"Error processing BNO055 data: {e}")
    # Hàm xử lý thông điệp log từ thiết bị
    def process_log_message(self, log_message):
        # Hiển thị log lên UI
        self.gui.update_monitor(f"Device log: {log_message}")
        
        # Ghi log nếu được bật
        self.setup_log_file("log")
        if self.log_data and "log" in self.log_files:
            timestamp = time.time() - self.start_times["log"]
            self.log_files["log"].write(f"{timestamp:.3f} {log_message}\n")
            self.log_files["log"].flush()


    def receive_client_data(self, sock):
        buffer = ""  # Lưu dữ liệu bị phân mảnh
        
        try:
            while self.control_active:
                try:
                    data = sock.recv(1024).decode()
                    if not data:
                        self.gui.update_monitor("Control client disconnected")
                        break

                    buffer += data  # Thêm dữ liệu mới vào buffer
                    
                    while "\n" in buffer:  # Kiểm tra nếu có dòng kết thúc
                        line, buffer = buffer.split("\n", 1)  # Lấy một dòng hoàn chỉnh
                        line = line.strip()  # Loại bỏ ký tự trắng thừa

                        # Phân tích dữ liệu JSON
                        try:
                            json_data = json.loads(line)
                            # Kiểm tra trường type
                            if "type" in json_data:
                                message_type = json_data["type"]

                                # Phân phối dữ liệu dựa vào loại
                                if message_type == "encoder" and "data" in json_data:
                                    self.process_encoder_data(json_data["data"])
                                    
                                elif message_type == "bno055" and "data" in json_data:
                                    self.process_bno055_data(json_data["data"])
                                    
                                elif message_type == "log" and "message" in json_data:
                                    self.process_log_message(json_data["message"])
                                    
                                else:
                                    self.gui.update_monitor(f"Unknown message type or missing data: {json_data}")
                            
                            else:
                                self.gui.update_monitor(f"Missing type field in JSON: {json_data}")
                                
                        except json.JSONDecodeError:
                            # Dữ liệu không đúng định dạng JSON
                            self.gui.update_monitor(f"Invalid JSON format: {line}")
                                
                except socket.timeout:
                    continue
                    
        except Exception as e:
            self.gui.update_monitor(f"Data reception error: {e}")
            print(f"Buffer at error: {buffer}")
        finally:
            # Đóng socket khi client ngắt kết nối
            try:
                if sock:
                    sock.close()
            except:
                pass
            if self.client_socket == sock:
                self.client_socket = None
            self.client_connected = False
            self.connection_status = "Disconnected"
            self.gui.update_status("Disconnected")
            self.gui.disable_control_buttons()
            self.close_all_logs()

    def send_command(self, dot_x, dot_y, dot_theta):
        # Gửi lệnh điều khiển đến client
        if not self.client_connected:
            print("Not connected - can't send command")
            return
            
        command = f"dot_x:{dot_x:.4f} dot_y:{dot_y:.4f} dot_theta:{dot_theta:.4f}"
        
        try:
            self.client_socket.sendall(command.encode())
            # Thêm log chi tiết nếu cần
            if abs(dot_x) > 0.01 or abs(dot_y) > 0.01 or abs(dot_theta) > 0.01:
                print(f"Sent: {command}")
        except Exception as e:
            print(f"Send command error: {e}")
            self.gui.update_monitor(f"Command send error: {e}")
        

    def set_speed(self, motor_index, speed):
        if not self.client_connected:
            self.gui.update_monitor("Not connected - can't set speed")
            return
            
        self.speed[motor_index] = speed
        try:
            command = f"MOTOR_{motor_index + 1}_SPEED:{speed}"
            self.client_socket.sendall(command.encode())
            self.gui.update_monitor(f"Motor {motor_index + 1} speed updated to {speed}")
        except Exception as e:
            self.gui.update_monitor(f"Error setting speed: {e}")

    def emergency_stop(self):
        """Send emergency stop command to all motors"""
        if not self.client_connected:
            return
            
        try:
            self.client_socket.sendall(b"EMERGENCY_STOP")
            self.gui.update_monitor("EMERGENCY STOP sent")
            
            # Also reset all local speed values
            for i in range(3):
                self.speed[i] = 0
                self.gui.update_speed_entry(i, 0)
        except Exception as e:
            self.gui.update_monitor(f"Error sending emergency stop: {e}")

    def send_set_pid(self):
        if not self.client_connected:
            messagebox.showerror("Error", "No client connected")
            return
            
        try:
            self.client_socket.sendall(b"Set PID")
            self.gui.update_monitor("Sent 'Set PID' command to the client.")
        except Exception as e:
            self.gui.update_monitor(f"Failed to send 'Set PID' command: {e}")

    def show_rpm_plot(self):
        """Display the RPM plot window"""
        rpm_plotter.show_plot()
        self.gui.update_monitor("RPM monitoring plot displayed")

    def set_pid_values(self, motor_index, p, i, d):
        if not self.client_connected:
            self.gui.update_monitor("Not connected - can't set PID values")
            return
            
        self.pid_values[motor_index] = [p, i, d]
        try:
            pid_command = f"MOTOR:{motor_index + 1} Kp:{p} Ki:{i} Kd:{d}"
            self.client_socket.sendall(pid_command.encode())
            self.gui.update_monitor(f"PID values set: MOTOR:{motor_index + 1} Kp:{p} Ki:{i} Kd:{d}")
        except Exception as e:
            self.gui.update_monitor(f"Error setting PID values: {e}")

    def save_pid_config(self):
        """Save current PID configuration to file"""
        try:
            with open("pid_config.txt", "w") as f:
                for idx, (p, i, d) in enumerate(self.pid_values):
                    # Đảm bảo giá trị là số thực
                    p_float = float(p)
                    i_float = float(i)
                    d_float = float(d)
                    f.write(f"Motor{idx+1}:{p_float},{i_float},{d_float}\n")
            self.gui.update_monitor("PID configuration saved successfully")
        except Exception as e:
            self.gui.update_monitor(f"Error saving PID config: {e}")

    def load_pid_config(self):
        """Load PID configuration from file"""
        try:
            with open("pid_config.txt", "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    parts = line.strip().split(":")
                    if len(parts) != 2:
                        continue
                    motor_name, values = parts
                    # Xử lý đúng định dạng - chuyển sang float rồi sang int
                    motor_str = motor_name.replace("Motor", "")
                    try:
                        motor_index = int(float(motor_str)) - 1
                    except ValueError:
                        self.gui.update_monitor(f"Invalid motor number: {motor_str}")
                        continue
                    
                    p, i, d = map(float, values.split(","))
                    self.pid_values[motor_index] = [p, i, d]
                    self.gui.update_pid_entries(motor_index, p, i, d)
            self.gui.update_monitor("PID configuration loaded")
        except FileNotFoundError:
            self.gui.update_monitor("PID config file not found")
        except Exception as e:
            self.gui.update_monitor(f"Error loading PID config: {e}")


class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.server = Server(self)
        self.encoder_labels = []
        self.speed_entries = []
        self.pid_entries = []
        self.control_gui = ControlGUI(root)
        self.control_gui.set_server(self.server)
        self.setup_gui()

    def setup_gui(self):
        self.root.title("Omni Robot Server Control")
        self.root.geometry("850x700")
        
        # Configure styles
        style = ttk.Style()
        style.configure("TButton", padding=5, relief="flat", background="#4CAF50")
        style.configure("Red.TButton", background="#F44336", foreground="white")
        style.configure("Green.TButton", background="#4CAF50", foreground="white")
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Status bar at top
        status_frame = ttk.Frame(main_frame, relief="sunken", padding="2")
        status_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(status_frame, text="Status:").pack(side="left")
        self.status_label = ttk.Label(status_frame, text="Disconnected")
        self.status_label.pack(side="left", padx=(5, 0))

        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True)
        
        # Create tabs
        firmware_tab = ttk.Frame(notebook, padding=10)
        control_tab = ttk.Frame(notebook, padding=10)
        settings_tab = ttk.Frame(notebook, padding=10)
        
        notebook.add(firmware_tab, text="Firmware Update")
        notebook.add(control_tab, text="Robot Control")
        notebook.add(settings_tab, text="Settings")
        
        # Firmware Tab
        firmware_frame = ttk.LabelFrame(firmware_tab, text="Firmware Management", padding=10)
        firmware_frame.pack(fill="x", pady=5)
        
        ttk.Button(firmware_frame, text="Start Firmware Server", 
                  command=self.server.start_firmware_server).grid(row=0, column=0, padx=5, pady=5)
        
        self.choose_file_button = ttk.Button(firmware_frame, text="Choose Firmware", 
                                       command=self.choose_file, state="disabled")
        self.choose_file_button.grid(row=0, column=1, padx=5, pady=5)
        
        self.send_firmware_button = ttk.Button(firmware_frame, text="Send Firmware", 
                                        command=self.server.send_firmware, state="disabled")
        self.send_firmware_button.grid(row=0, column=2, padx=5, pady=5)
        
        self.switch_upgrade_button = ttk.Button(firmware_frame, text="Switch to Upgrade Mode", 
                                         command=self.server.send_upgrade_command,
                                         state="disabled")  # Bắt đầu với trạng thái disabled
        self.switch_upgrade_button.grid(row=0, column=3, padx=5, pady=5)
        
        # Progress bar (hidden initially)
        self.progress_var = tk.DoubleVar()
        self.progress_frame = ttk.Frame(firmware_tab)
        ttk.Label(self.progress_frame, text="Upload progress:").pack(side="left")
        self.progress_bar = ttk.Progressbar(self.progress_frame, 
                                           variable=self.progress_var,
                                           maximum=100, length=400)
        self.progress_bar.pack(side="left", padx=5)
        
        # Control Tab
        control_frame = ttk.LabelFrame(control_tab, text="Robot Control", padding=10)
        control_frame.pack(fill="x", pady=5)
        
        ttk.Button(control_frame, text="Start Control Server", 
                  command=self.server.start_control_server).grid(row=0, column=0, padx=5, pady=5)
        
        ttk.Button(control_frame, text="Stop Server", 
                  command=self.server.stop_control_server).grid(row=0, column=1, padx=5, pady=5)
                  
        self.manual_control_button = ttk.Button(control_frame, text="Manual Control", 
                                         command=self.manual_control, state="normal")
        self.manual_control_button.grid(row=0, column=2, padx=5, pady=5)
        
        emerg_button = ttk.Button(control_frame, text="EMERGENCY STOP", 
                                  command=self.server.emergency_stop, style="Red.TButton")
        emerg_button.grid(row=0, column=3, padx=5, pady=5)
        
        # Motor control frame
        motor_frame = ttk.LabelFrame(control_tab, text="Motor Control", padding=10)
        motor_frame.pack(fill="x", pady=5)
        
        # Labels for the columns
        ttk.Label(motor_frame, text="Motor").grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(motor_frame, text="Speed").grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(motor_frame, text="Action").grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(motor_frame, text="Current RPM").grid(row=0, column=3, padx=5, pady=5)
        
        self.speed_entries = []
        
        for i in range(3):
            ttk.Label(motor_frame, text=f"Motor {i+1}:").grid(row=i+1, column=0, padx=5, pady=5)
            
            speed_entry = ttk.Entry(motor_frame, width=7)
            speed_entry.insert(0, "0")
            speed_entry.grid(row=i+1, column=1, padx=5, pady=5)
            self.speed_entries.append(speed_entry)
            
            set_button = ttk.Button(motor_frame, text="Set", 
                                   command=lambda idx=i, e=speed_entry: self.set_motor_speed(idx, e))
            set_button.grid(row=i+1, column=2, padx=5, pady=5)
            
            encoder_label = ttk.Label(motor_frame, text=f"RPM: 0")
            self.encoder_labels.append(encoder_label)
            encoder_label.grid(row=i+1, column=3, padx=5, pady=5)
            
        # PID control frame
        pid_frame = ttk.LabelFrame(control_tab, text="PID Control", padding=10)
        pid_frame.pack(fill="x", pady=5)
        
        # Buttons for PID control
        ttk.Button(pid_frame, text="Start PID Monitor", 
                  command=self.server.send_set_pid).grid(row=0, column=0, padx=5, pady=5)
                  
        ttk.Button(pid_frame, text="Show RPM Plot", 
                  command=self.server.show_rpm_plot).grid(row=0, column=1, padx=5, pady=5)
                  
        ttk.Button(pid_frame, text="Save PID Config", 
                  command=self.server.save_pid_config).grid(row=0, column=2, padx=5, pady=5)
                  
        ttk.Button(pid_frame, text="Load PID Config", 
                  command=self.server.load_pid_config).grid(row=0, column=3, padx=5, pady=5)
        
        # Labels for PID columns
        ttk.Label(pid_frame, text="Motor").grid(row=1, column=0, padx=5, pady=5)
        ttk.Label(pid_frame, text="Kp").grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(pid_frame, text="Ki").grid(row=1, column=2, padx=5, pady=5)
        ttk.Label(pid_frame, text="Kd").grid(row=1, column=3, padx=5, pady=5)
        ttk.Label(pid_frame, text="Action").grid(row=1, column=4, padx=5, pady=5)
        
        self.pid_entries = []
        
        for i in range(3):
            ttk.Label(pid_frame, text=f"Motor {i+1}:").grid(row=i+2, column=0, padx=5, pady=5)
            
            p_entry = ttk.Entry(pid_frame, width=7)
            i_entry = ttk.Entry(pid_frame, width=7)
            d_entry = ttk.Entry(pid_frame, width=7)
            p_entry.insert(0, "0")
            i_entry.insert(0, "0")
            d_entry.insert(0, "0")
            p_entry.grid(row=i+2, column=1, padx=5, pady=5)
            i_entry.grid(row=i+2, column=2, padx=5, pady=5)
            d_entry.grid(row=i+2, column=3, padx=5, pady=5)
            self.pid_entries.append((p_entry, i_entry, d_entry))
            
            set_button = ttk.Button(pid_frame, text="Set", 
                                  command=lambda idx=i: self.set_pid(idx))
            set_button.grid(row=i+2, column=4, padx=5, pady=5)
            
        # Settings Tab
        log_frame = ttk.LabelFrame(settings_tab, text="Logging Settings", padding=10)
        log_frame.pack(fill="x", pady=5)
        
        self.log_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_frame, text="Enable data logging", 
                       variable=self.log_var, 
                       command=self.toggle_logging).pack(anchor="w")
                       
        # Monitor Section (put at bottom of the window)
        monitor_frame = ttk.LabelFrame(main_frame, text="Status Monitor", padding=5)
        monitor_frame.pack(fill="both", expand=True, pady=10)
        
        # Create a frame for the monitor text and scrollbar
        text_frame = ttk.Frame(monitor_frame)
        text_frame.pack(fill="both", expand=True)
        
        self.monitor_text = tk.Text(text_frame, height=10, width=80, wrap="word")
        self.monitor_text.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, command=self.monitor_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.monitor_text.config(yscrollcommand=scrollbar.set)
        
        # Button to clear monitor
        ttk.Button(monitor_frame, text="Clear Monitor", 
                  command=self.clear_monitor).pack(anchor="e", pady=(5, 0))
                  
        # Initialize with a welcome message
        self.update_monitor("Server interface initialized. Ready to start.")

    def toggle_logging(self):
        self.server.log_data = self.log_var.get()
        self.update_monitor(f"Data logging {'enabled' if self.server.log_data else 'disabled'}")

    def clear_monitor(self):
        self.monitor_text.delete(1.0, tk.END)
        self.update_monitor("Monitor cleared")

    def setup_progress_bar(self, total_size):
        """Setup and show progress bar for file upload"""
        self.progress_frame.pack(fill="x", pady=10)
        self.progress_var.set(0)
        self.progress_bar.configure(maximum=total_size)

    def update_progress(self, value):
        """Update progress bar value"""
        self.progress_var.set(value)
        self.root.update_idletasks()

    def hide_progress_bar(self):
        """Hide progress bar when not needed"""
        self.progress_frame.pack_forget()

    def update_status(self, status):
        """Update connection status"""
        self.status_label.config(text=status)

    def set_pid(self, motor_index):
        try:
            p = float(self.pid_entries[motor_index][0].get())
            i = float(self.pid_entries[motor_index][1].get())
            d = float(self.pid_entries[motor_index][2].get())
            self.server.set_pid_values(motor_index, p, i, d)
        except ValueError:
            self.update_monitor(f"Invalid PID values for Motor {motor_index + 1}.")
            messagebox.showerror("Error", f"Invalid PID values for Motor {motor_index + 1}")

    def update_pid_entries(self, motor_index, p, i, d):
        """Update PID entry fields with loaded values"""
        self.pid_entries[motor_index][0].delete(0, tk.END)
        self.pid_entries[motor_index][0].insert(0, str(p))
        self.pid_entries[motor_index][1].delete(0, tk.END)
        self.pid_entries[motor_index][1].insert(0, str(i))
        self.pid_entries[motor_index][2].delete(0, tk.END)
        self.pid_entries[motor_index][2].insert(0, str(d))

    def choose_file(self):
        """Open file dialog to select firmware file"""
        file_path = filedialog.askopenfilename(
            title="Select Firmware File",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if file_path:
            self.server.file_path = file_path
            self.update_monitor(f"Selected firmware file: {file_path}")
            self.send_firmware_button.config(state="normal")

    def enable_file_selection(self):
        """Enable firmware file selection buttons"""
        self.choose_file_button.config(state="normal")

    def enable_control_buttons(self):
        """Enable control buttons when connected"""
        self.manual_control_button.config(state="normal")
        # Bật nút Switch Upgrade Mode khi client kết nối vào control server
        self.switch_upgrade_button.config(state="normal")

    def disable_buttons(self):
        """Disable all buttons when disconnected"""
        self.choose_file_button.config(state="disabled")
        self.send_firmware_button.config(state="disabled")
        self.switch_upgrade_button.config(state="disabled")

    def disable_control_buttons(self):
        """Disable control buttons when disconnected"""
        # The manual control button can remain enabled since it opens a separate window
        # Tắt nút Switch Upgrade Mode khi client ngắt kết nối
        self.switch_upgrade_button.config(state="disabled")
    
    def update_encoders(self, encoders):
        """Update the encoder labels with new values"""
        for i, value in enumerate(encoders):
            self.encoder_labels[i].config(text=f"RPM: {value:.1f}")

    def update_monitor(self, message):
        """Add message to the monitor with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.monitor_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.monitor_text.see(tk.END)  # Scroll to the end

    def update_speed_entry(self, motor_index, speed):
        """Update the motor speed entry field"""
        self.speed_entries[motor_index].delete(0, tk.END)
        self.speed_entries[motor_index].insert(0, str(speed))

    def set_motor_speed(self, motor_index, entry):
        """Set motor speed from UI entry field"""
        try:
            speed = float(entry.get())
            self.server.set_speed(motor_index, speed)
        except ValueError:
            self.update_monitor(f"Invalid speed value for Motor {motor_index + 1}")
            messagebox.showerror("Error", f"Invalid speed value for Motor {motor_index + 1}")

    def manual_control(self):
        """Open manual control window for robot navigation"""
        self.control_gui.run()
        self.update_monitor("Manual control window opened")

if __name__ == "__main__":
    root = tk.Tk()
    gui = ServerGUI(root)
    root.mainloop()