# Tạo file start_system.bat
start cmd /k "cd d:\WebDashboard\back && python tcp_server.py"
timeout /t 5
start cmd /k "cd d:\WebDashboard\back && python main.py"
timeout /t 5
start cmd /k "cd d:\WebDashboard\front && npm start"