import React, { useState, useEffect } from "react";
import { RotateCcw, Send } from "lucide-react";
import { useRobotWebSocket } from '../services/WebSocketManager';
import WidgetConnectionHeader from "./WidgetConnectionHeader";

interface MotorData {
  id: number;
  name: string;
  speed: number;
  rpm: number;
}

const MotorControlWidget: React.FC = () => {
  const [motors, setMotors] = useState<MotorData[]>([
    { id: 1, name: "Motor 1", speed: 0, rpm: 0 },
    { id: 2, name: "Motor 2", speed: 0, rpm: 0 },
    { id: 3, name: "Motor 3", speed: 0, rpm: 0 },
  ]);
  
  // Keep track of pending changes
  const [pendingMotors, setPendingMotors] = useState<MotorData[]>([
    { id: 1, name: "Motor 1", speed: 0, rpm: 0 },
    { id: 2, name: "Motor 2", speed: 0, rpm: 0 },
    { id: 3, name: "Motor 3", speed: 0, rpm: 0 },
  ]);
  
  const [robotId, setRobotId] = useState<string>("robot1");
  const [error, setError] = useState<string>("");
  
  const {
    status,
    isConnected,
    sendMessage,
    connect, 
    disconnect
  } = useRobotWebSocket(robotId, {
    autoConnect: false,
    onMessage: (data: any) => {
      try {
        // Xử lý dữ liệu cập nhật từ motor
        if (data.motor && data.motor.speeds) {
          const newMotors = [...motors];
          data.motor.speeds.forEach((rpm: number, idx: number) => {
            if (idx < newMotors.length) {
              newMotors[idx].rpm = rpm;
            }
          });
          setMotors(newMotors);
        } 
      } catch (e) {
        console.error("Error processing message", e);
      }
    },
    onConnect: () => {
      console.log(`Connected to ${robotId}`);
      setError("");
    },
    onDisconnect: () => {
      console.log(`Disconnected from ${robotId}`);
    },
    onError: () => {
      console.log(`Error connecting to ${robotId}`);
      setError("Lỗi kết nối WebSocket");
      setTimeout(() => setError(""), 3000);
    }
  });

  const handleRobotChange = (newRobotId: string) => {
    if (isConnected) {
      disconnect();
      setTimeout(() => {
        setRobotId(newRobotId);
        setTimeout(connect, 100);
      }, 300);
    } else {
      setRobotId(newRobotId);
    }
  };
  
  // Update pending motor speed without sending command
  const updatePendingSpeed = (motorId: number, speed: number) => {
    const newPendingMotors = [...pendingMotors];
    const idx = newPendingMotors.findIndex(m => m.id === motorId);
    if (idx !== -1) {
      newPendingMotors[idx].speed = speed;
      setPendingMotors(newPendingMotors);
    }
  };
  
  // Send all motor speeds at once
  const sendAllMotorSpeeds = () => {
    if (!isConnected) {
      setError("WebSocket chưa kết nối!");
      setTimeout(() => setError(""), 3000);
      return;
    }
    
    // Get all speeds from pending motors
    const speeds = pendingMotors.map(m => m.speed);
    
    // Update actual motor state
    setMotors([...pendingMotors]);
    
    // Send command with all motor speeds
    sendMessage({
      type: "motor_control",  // Changed from "motor" to "motor_control"
      speeds: speeds,
      robot_id: robotId
    });
    
    console.log(`Sent speeds to all motors: ${speeds.join(', ')}`);
  };
  
  // Hàm dừng khẩn cấp
  const emergencyStop = () => {
    if (!isConnected) {
      setError("WebSocket chưa kết nối!");
      setTimeout(() => setError(""), 3000);
      return;
    }
    
    // Cập nhật trạng thái UI
    const stoppedMotors = pendingMotors.map(m => ({...m, speed: 0}));
    setMotors(stoppedMotors);
    setPendingMotors(stoppedMotors);
    
    // Gửi lệnh dừng khẩn cấp
    sendMessage({
      type: "emergency_stop",
      robot_id: robotId
    });
  };
  
  return (
    <div className="p-4 bg-white rounded-lg shadow-md">
      <WidgetConnectionHeader
        title="Điều khiển động cơ"
        status={status}
        isConnected={isConnected}
        onConnect={connect}
        onDisconnect={disconnect}
      />
      
      {/* Thêm UI để chọn robot */}
      <div className="flex justify-between mb-4">
        <h2 className="text-lg font-semibold">Điều khiển động cơ</h2>
        <div className="flex items-center gap-2">
          <select 
            value={robotId}
            onChange={(e) => handleRobotChange(e.target.value)}
            className="border rounded px-2 py-1 text-sm"
          >
            <option value="robot1">Robot 1</option>
            <option value="robot2">Robot 2</option>
            <option value="robot3">Robot 3</option>
            <option value="robot4">Robot 4</option>
          </select>
        </div>
      </div>
      
      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-2 mb-4">
          {error}
        </div>
      )}
      
      <div className="grid gap-3 mb-4">
        {pendingMotors.map((motor, index) => (
          <div key={index} className="grid grid-cols-3 gap-2 items-center border-b last:border-b-0 pb-2">
            <div className="font-semibold">{motor.name}</div>
            
            <input
              type="number"
              value={motor.speed}
              onChange={(e) => updatePendingSpeed(motor.id, parseFloat(e.target.value) || 0)}
              className="border rounded-md px-2 py-1 text-sm w-24"
              disabled={!isConnected}
            />
            
            <div className="flex items-center gap-1">
              <RotateCcw 
                size={16} 
                className={`${motors.find(m => m.id === motor.id)?.rpm || 0 > 0 ? 
                  "text-green-600 animate-spin" : 
                  "text-gray-400"}`} 
              />
              <span className="font-mono">
                {(motors.find(m => m.id === motor.id)?.rpm || 0).toFixed(1)} RPM
              </span>
            </div>
          </div>
        ))}
      </div>
      
      {/* Single set button for all motors */}
      <div className="flex justify-between gap-2">
        <button
          onClick={sendAllMotorSpeeds}
          disabled={!isConnected}
          className="flex-1 bg-green-600 text-white px-3 py-2 rounded-md text-sm hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <Send size={16} />
          <span>Cài đặt tốc độ cho tất cả động cơ</span>
        </button>
        
        <button
          onClick={emergencyStop}
          disabled={!isConnected}
          className="bg-red-600 text-white px-3 py-2 rounded-md text-sm hover:bg-red-700 disabled:bg-red-400 disabled:cursor-not-allowed"
        >
          DỪNG KHẨN CẤP
        </button>
      </div>
    </div>
  );
};

export default MotorControlWidget;