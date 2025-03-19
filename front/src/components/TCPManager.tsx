// TCPManager.tsx
import React, { useState, useEffect } from "react";

const TCPManager: React.FC = () => {
  const [socket, setSocket] = useState<any>(null);
  const [status, setStatus] = useState("Chưa kết nối TCP");
  const [robotID, setRobotID] = useState("robot01");
  const [command, setCommand] = useState("");

  useEffect(() => {
    // Ví dụ: Thử mở kết nối TCP đến localhost:5005
    // Yêu cầu Node context/Electron, v.v.:
    try {
      const net = require("net");
      const client = new net.Socket();

      client.connect(5005, "127.0.0.1", () => {
        console.log("Đã kết nối TCP tới server!");
        setStatus("Đã kết nối TCP");
        // Gửi ID? => Giả sử dashboard
        client.write("dashboard01\n");
      });

      client.on("data", (data: Buffer) => {
        console.log("TCP nhận:", data.toString());
      });

      client.on("error", (err: any) => {
        console.error("TCP Lỗi:", err);
        setStatus("TCP error: " + err.message);
      });

      client.on("close", () => {
        console.log("TCP đóng.");
        setStatus("TCP đóng");
      });

      setSocket(client);
    } catch (err) {
      console.error("Không thể khởi tạo TCP client (môi trường browser?).", err);
    }
  }, []);

  const sendCommand = () => {
    if (!socket) {
      alert("Socket chưa sẵn sàng.");
      return;
    }
    // Giả sử format JSON: {"robot":"robot01","command":"move_forward"}
    const msgObj = { robot: robotID, command: command };
    const msgStr = JSON.stringify(msgObj) + "\n"; // Thêm xuống dòng
    socket.write(msgStr);
    console.log("Đã gửi:", msgStr);
  };

  return (
    <div style={{ border: "1px solid #ddd", padding: 10 }}>
      <h3>Direct TCP Manager (Chỉ chạy nếu môi trường hỗ trợ)</h3>
      <p>Trạng thái: {status}</p>
      <div>
        <label>Robot ID: </label>
        <input value={robotID} onChange={e => setRobotID(e.target.value)} />
      </div>
      <div>
        <label>Command: </label>
        <input value={command} onChange={e => setCommand(e.target.value)} />
      </div>
      <button onClick={sendCommand}>Gửi Lệnh TCP</button>
    </div>
  );
};

export default TCPManager;
