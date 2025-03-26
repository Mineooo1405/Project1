@echo off
REM Script to start all components of the WebDashboard system

REM Set environment paths
SET PATH=%PATH%;C:\Python311;C:\Python311\Scripts;C:\Program Files\nodejs

REM Đặt biến môi trường với port
set TCP_PORT=9000
set WS_BRIDGE_PORT=9003
set LOG_LEVEL=INFO
set LOG_HEARTBEATS=0
set LOG_DETAILED_MESSAGES=1

REM Kill các tiến trình đang chạy
echo Stopping any running services...
taskkill /F /FI "WINDOWTITLE eq DirectBridge*" >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq FastAPI Backend*" >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq React Frontend*" >nul 2>nul

REM Giải phóng các port đang được sử dụng
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :%TCP_PORT%') do (
  echo Killing process using port %TCP_PORT% (PID: %%p)
  taskkill /F /PID %%p >nul 2>nul
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :%WS_BRIDGE_PORT%') do (
  echo Killing process using port %WS_BRIDGE_PORT% (PID: %%p)
  taskkill /F /PID %%p >nul 2>nul
)

IF NOT EXIST "d:\WebDashboard\back\.env" (
  echo Warning: Backend .env file not found. Creating default...
  copy NUL "d:\WebDashboard\back\.env"
  echo # Backend environment variables >> "d:\WebDashboard\back\.env"
  echo API_HOST=0.0.0.0 >> "d:\WebDashboard\back\.env"
  echo API_PORT=8000 >> "d:\WebDashboard\back\.env"
  echo TCP_HOST=0.0.0.0 >> "d:\WebDashboard\back\.env"
  echo TCP_PORT=%TCP_PORT% >> "d:\WebDashboard\back\.env"
  echo WS_BRIDGE_HOST=0.0.0.0 >> "d:\WebDashboard\back\.env"
  echo WS_BRIDGE_PORT=%WS_BRIDGE_PORT% >> "d:\WebDashboard\back\.env"
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
echo TCP_PORT=%TCP_PORT%>> "d:\WebDashboard\back\env_config.txt"
echo WS_BRIDGE_PORT=%WS_BRIDGE_PORT%>> "d:\WebDashboard\back\env_config.txt"

REM Display starting message
echo mStarting WebDashboard system...
echo.
echo This will start:
echo m1. DirectBridge (TCP port %TCP_PORT%, WebSocket port %WS_BRIDGE_PORT%)
echo m2. FastAPI Backend (port 8000)
echo m3. React Frontend (port 3000)
echo.
echo Press Ctrl+C in any window to stop that component
echo.

REM Create logs directory if it doesn't exist
if not exist "d:\WebDashboard\back\logs" mkdir "d:\WebDashboard\back\logs"

REM Start DirectBridge with environment variables
echo mStarting DirectBridge...
start cmd /k "title DirectBridge && cd /d d:\WebDashboard\back && set LOG_LEVEL=%LOG_LEVEL% && set LOG_HEARTBEATS=%LOG_HEARTBEATS% && set LOG_DETAILED_MESSAGES=%LOG_DETAILED_MESSAGES% && set TCP_PORT=%TCP_PORT% && set WS_BRIDGE_PORT=%WS_BRIDGE_PORT% && python direct_bridge.py"
timeout /t 5

REM Start FastAPI Backend
echo mStarting FastAPI Backend...
start cmd /k "title FastAPI Backend && cd /d d:\WebDashboard\back && set LOG_LEVEL=%LOG_LEVEL% && python main.py"
timeout /t 5

REM Start React Frontend (React automatically loads .env)
echo mStarting React Frontend...
start cmd /k "title React Frontend && cd /d d:\WebDashboard\front && npm start"

echo.
echo mAll components started!
echo.
echo System running at:
echo m- DirectBridge TCP Server: localhost:%TCP_PORT%
echo m- DirectBridge WebSocket: ws://localhost:%WS_BRIDGE_PORT%
echo m- FastAPI: http://localhost:8000
echo m- Frontend: http://localhost:3000
echo.
echo To stop all services, press any key to close this window, then run stop_system.bat
pause > nul