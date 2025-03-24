@echo off
REM Script to start all components of the WebDashboard system

REM Set environment paths
SET PATH=%PATH%;C:\Python311;C:\Python311\Scripts;C:\Program Files\nodejs

REM Đặt biến môi trường với port KHÁC NHAU
set WS_FRONTEND_PORT=9002
set WS_BRIDGE_PORT=9003
set LOG_LEVEL=INFO
set LOG_HEARTBEATS=0
set LOG_DETAILED_MESSAGES=1

REM Kill các tiến trình đang chạy
echo Stopping any running services...
taskkill /F /FI "WINDOWTITLE eq TCP Server*" >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq WebSocket Bridge*" >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq FastAPI Backend*" >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq React Frontend*" >nul 2>nul

REM Giải phóng các port đang được sử dụng
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :9002') do (
  echo Killing process using port 9002 (PID: %%p)
  taskkill /F /PID %%p >nul 2>nul
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :9003') do (
  echo Killing process using port 9003 (PID: %%p)
  taskkill /F /PID %%p >nul 2>nul
)

IF NOT EXIST "d:\WebDashboard\back\.env" (
  echo Warning: Backend .env file not found. Creating default...
  copy NUL "d:\WebDashboard\back\.env"
  echo # Backend environment variables >> "d:\WebDashboard\back\.env"
  echo API_HOST=0.0.0.0 >> "d:\WebDashboard\back\.env"
  echo API_PORT=8000 >> "d:\WebDashboard\back\.env"
  echo TCP_HOST=0.0.0.0 >> "d:\WebDashboard\back\.env"
  echo TCP_PORT=9000 >> "d:\WebDashboard\back\.env"
  echo WS_BRIDGE_HOST=0.0.0.0 >> "d:\WebDashboard\back\.env"
  echo WS_BRIDGE_PORT=%WS_BRIDGE_PORT% >> "d:\WebDashboard\back\.env"
  echo WS_FRONTEND_PORT=%WS_FRONTEND_PORT% >> "d:\WebDashboard\back\.env"
  echo LOG_LEVEL=%LOG_LEVEL% >> "d:\WebDashboard\back\.env"
  echo LOG_HEARTBEATS=%LOG_HEARTBEATS% >> "d:\WebDashboard\back\.env"
  echo LOG_DETAILED_MESSAGES=%LOG_DETAILED_MESSAGES% >> "d:\WebDashboard\back\.env"
)

IF NOT EXIST "d:\WebDashboard\front\.env" (
  echo Warning: Frontend .env file not found. Creating default...
  copy NUL "d:\WebDashboard\front\.env"
  echo # Frontend environment variables >> "d:\WebDashboard\front\.env"
  echo REACT_APP_API_URL=http://localhost:8000 >> "d:\WebDashboard\front\.env"
  echo REACT_APP_WS_URL=ws://localhost:8000/ws >> "d:\WebDashboard\front\.env"
  echo REACT_APP_WS_BRIDGE_URL=ws://localhost:%WS_BRIDGE_PORT% >> "d:\WebDashboard\front\.env"
)

REM Tạo file cấu hình tạm để bảo đảm không có khoảng trắng trong biến
echo LOG_LEVEL=%LOG_LEVEL%> "d:\WebDashboard\back\env_config.txt"
echo LOG_HEARTBEATS=%LOG_HEARTBEATS%>> "d:\WebDashboard\back\env_config.txt"
echo LOG_DETAILED_MESSAGES=%LOG_DETAILED_MESSAGES%>> "d:\WebDashboard\back\env_config.txt"
echo WS_BRIDGE_PORT=%WS_BRIDGE_PORT%>> "d:\WebDashboard\back\env_config.txt"
echo WS_FRONTEND_PORT=%WS_FRONTEND_PORT%>> "d:\WebDashboard\back\env_config.txt"

REM Display starting message
echo [92mStarting WebDashboard system...[0m
echo.
echo This will start:
echo [94m1. TCP Server (port 9000, WebSocket frontend: port %WS_FRONTEND_PORT%)[0m
echo [94m2. WebSocket Bridge (port %WS_BRIDGE_PORT%)[0m
echo [94m3. FastAPI Backend (port 8000)[0m
echo [94m4. React Frontend (port 3000)[0m
echo.
echo Press Ctrl+C in any window to stop that component
echo.

REM Create logs directory if it doesn't exist
if not exist "d:\WebDashboard\back\logs" mkdir "d:\WebDashboard\back\logs"

REM Start TCP Server with environment variables
echo [92mStarting TCP Server...[0m
start cmd /k "title TCP Server && cd /d d:\WebDashboard\back && set LOG_LEVEL=%LOG_LEVEL% && set LOG_HEARTBEATS=%LOG_HEARTBEATS% && set LOG_DETAILED_MESSAGES=%LOG_DETAILED_MESSAGES% && set WS_FRONTEND_PORT=%WS_FRONTEND_PORT% && python tcp_server.py"
timeout /t 5

REM Start WebSocket Bridge
echo [92mStarting WebSocket Bridge...[0m
start cmd /k "title WebSocket Bridge && cd /d d:\WebDashboard\back && set LOG_LEVEL=%LOG_LEVEL% && set LOG_HEARTBEATS=%LOG_HEARTBEATS% && set LOG_DETAILED_MESSAGES=%LOG_DETAILED_MESSAGES% && set WS_BRIDGE_PORT=%WS_BRIDGE_PORT% && python ws_tcp_bridge.py"
timeout /t 3

REM Start FastAPI Backend
echo [92mStarting FastAPI Backend...[0m
start cmd /k "title FastAPI Backend && cd /d d:\WebDashboard\back && set LOG_LEVEL=%LOG_LEVEL% && python main.py"
timeout /t 5

REM Start React Frontend (React automatically loads .env)
echo [92mStarting React Frontend...[0m
start cmd /k "title React Frontend && cd /d d:\WebDashboard\front && npm start"

echo.
echo [92mAll components started![0m
echo.
echo System running at:
echo [94m- TCP Server: localhost:9000[0m
echo [94m- TCP WebSocket Frontend: ws://localhost:%WS_FRONTEND_PORT%[0m 
echo [94m- WebSocket Bridge: ws://localhost:%WS_BRIDGE_PORT%[0m
echo [94m- FastAPI: http://localhost:8000[0m
echo [94m- Frontend: http://localhost:3000[0m
echo.
echo To stop all services, press any key to close this window, then run stop_system.bat
pause > nul