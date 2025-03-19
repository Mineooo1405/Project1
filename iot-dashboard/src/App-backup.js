import logo from './logo.svg';
import './App.css';
import { useEffect, useRef, useState } from "react";

function App() {
  const [robotStates, setRobotStates] = useState({});   // trạng thái các robot
  const ws = useRef(null);

  const sendCommand = (robotId, command) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const message = `${robotId}:${command}`;
      ws.current.send(message);
      console.log("Sent:", message);
    }
  };
  useEffect(() => {
    // Kết nối WebSocket tới FastAPI
    ws.current = new WebSocket("ws://localhost:8000/ws/dashboard");
    ws.current.onopen = () => {
      console.log("Connected to WebSocket server");
    };
    ws.current.onmessage = (event) => {
      const message = event.data;
      console.log("Received from server:", message);
      // Xử lý thông điệp trạng thái từ server
      // Giả sử server gửi dạng "robotId:status"
      if (message.includes(":")) {
        const [robotId, status] = message.split(":");
        setRobotStates(prev => ({ ...prev, [robotId]: status }));
      }
    };
    ws.current.onclose = () => {
      console.log("WebSocket disconnected");
    };
    // Đóng kết nối khi component unmount
    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);
  
  return (
    <div className="dashboard">
      <h1>Robot Dashboard</h1>
      <div className="robot-status-list">
        {[1,2,3,4].map(id => (
          <div key={id} className="robot-card">
            <h2>Robot {id}</h2>
            <p>Trạng thái: {robotStates[id] || "N/A"}</p>
            {/* Các nút điều khiển cho robot này */}
            <button onClick={() => sendCommand(id, "forward")}>Tiến</button>
            <button onClick={() => sendCommand(id, "backward")}>Lùi</button>
            <button onClick={() => sendCommand(id, "left")}>Trái</button>
            <button onClick={() => sendCommand(id, "right")}>Phải</button>
          </div>
        ))}
      </div>
      {/* Nút điều khiển tất cả robot */}
      <div className="all-controls">
        <h2>Điều khiển đồng thời</h2>
        <button onClick={() => sendCommand("all", "forward")}>Tất cả Tiến</button>
        <button onClick={() => sendCommand("all", "stop")}>Tất cả Dừng</button>
        {/* ... */}
      </div>
    </div>
  );
}

export default App;
