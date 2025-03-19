import React, { useState, useCallback } from "react";
import { useRobotWebSocket } from '../services/WebSocketManager';
import WidgetConnectionHeader from "./WidgetConnectionHeader";

interface RPMData {
  [key: number]: number; // motor_id -> RPM value
}

// Định nghĩa kiểu dữ liệu cho messages WebSocket
type WebSocketMessage = {
  type: string;
  rpm?: RPMData | number[];
  status?: string;
  message?: string;
  [key: string]: any;
};

const RobotControlWidget: React.FC = () => {
  const [motorSpeeds, setMotorSpeeds] = useState<number[]>([0, 0, 0]);
  const [rpmValues, setRpmValues] = useState<RPMData>({1: 0, 2: 0, 3: 0});
  const [robotId, setRobotId] = useState<string>("robot1");
  const [errorMessage, setErrorMessage] = useState<string>("");
  
  // Sửa cách gọi useRobotWebSocket để phù hợp với phiên bản đơn giản hóa
  // ⚠️ Lưu ý: useRobotWebSocket bây giờ nhận trực tiếp robotId làm tham số đầu tiên
  const {
    status,
    isConnected,
    sendMessage,
    connect,
    disconnect
  } = useRobotWebSocket(robotId, {
    autoConnect: false,
    onMessage: (data: WebSocketMessage) => {
      try {
        if (data.type === "update" && data.rpm) {
          setRpmValues(typeof data.rpm === 'object' ? data.rpm : 
            Array.isArray(data.rpm) ? {1: data.rpm[0] || 0, 2: data.rpm[1] || 0, 3: data.rpm[2] || 0} : 
            rpmValues);
        } else if (data.type === "init_motor_data" && data.rpm) {
          // Initialize motor RPM data when first connecting
          setRpmValues(typeof data.rpm === 'object' && !Array.isArray(data.rpm) ? data.rpm : 
            Array.isArray(data.rpm) ? {1: data.rpm[0] || 0, 2: data.rpm[1] || 0, 3: data.rpm[2] || 0} :
            rpmValues);
        } else if (data.status === "error") {
          setErrorMessage(data.message || "An error occurred");
          setTimeout(() => setErrorMessage(""), 5000);
        }
      } catch (e) {
        console.error("Error processing message", e);
      }
    },
    onConnect: () => {
      console.log("Motor control WebSocket connected");
      setErrorMessage("");
      
      // Yêu cầu dữ liệu ban đầu khi kết nối
      sendMessage({
        type: "get_motor_data",
        robot_id: robotId
      });
    },
    onDisconnect: () => {
      console.log("Motor control WebSocket disconnected");
    },
    onError: () => {
      setErrorMessage("Failed to connect to motor control server");
      setTimeout(() => setErrorMessage(""), 5000);
    }
  });

  // Hàm xử lý khi thay đổi robot - cải tiến theo phiên bản mới
  const handleRobotChange = useCallback((newRobotId: string) => {
    if (isConnected) {
      disconnect();
      // Đợi ngắt kết nối hoàn tất
      setTimeout(() => {
        setRobotId(newRobotId);
        // Đợi state cập nhật
        setTimeout(() => {
          connect();
        }, 100);
      }, 300);
    } else {
      setRobotId(newRobotId);
    }
  }, [isConnected, disconnect, connect]);

  const setMotorSpeed = useCallback((motorId: number, speed: number): void => {
    if (!isConnected) {
      setErrorMessage("WebSocket not connected!");
      setTimeout(() => setErrorMessage(""), 5000);
      return;
    }
    
    // Update local state
    const newSpeeds = [...motorSpeeds];
    newSpeeds[motorId-1] = speed;
    setMotorSpeeds(newSpeeds);
    
    // Send command to backend
    const command = {
      type: "motor_control",
      motor_id: motorId,
      speed: speed
    };
    sendMessage(command);
  }, [isConnected, motorSpeeds, sendMessage]);

  const emergencyStop = useCallback((): void => {
    if (!isConnected) {
      setErrorMessage("WebSocket not connected!");
      setTimeout(() => setErrorMessage(""), 5000);
      return;
    }
    
    // Reset all speeds locally
    setMotorSpeeds([0, 0, 0]);
    
    // Send emergency stop
    const command = {
      type: "emergency_stop"
    };
    sendMessage(command);
  }, [isConnected, sendMessage]);

  return (
    <div className="p-4 bg-white rounded-lg shadow-md">
      {/* Thêm WidgetConnectionHeader cho giao diện nhất quán */}
      <WidgetConnectionHeader
        title="Robot Control"
        status={status}
        isConnected={isConnected}
        onConnect={connect}
        onDisconnect={disconnect}
      />
      
      <div className="flex justify-between mb-4">
        <h2 className="text-lg font-semibold">Robot Control</h2>
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
      
      {errorMessage && (
        <div className="bg-red-100 text-red-700 p-2 rounded-md text-sm mb-2">
          {errorMessage}
        </div>
      )}
      
      <div className="grid grid-cols-4 gap-2 text-sm font-bold border-b pb-2">
        <div>Motor</div>
        <div>Speed</div>
        <div>Action</div>
        <div>Current RPM</div>
      </div>
      
      {[1, 2, 3].map((motorId) => (
        <div key={motorId} className="grid grid-cols-4 gap-2 items-center py-2 border-b last:border-b-0">
          <div>Motor {motorId}</div>
          <input 
            type="number" 
            value={motorSpeeds[motorId-1]}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              const newSpeeds = [...motorSpeeds];
              newSpeeds[motorId-1] = parseInt(e.target.value) || 0;
              setMotorSpeeds(newSpeeds);
            }}
            className="border rounded px-2 py-1 w-full"
            disabled={!isConnected}
          />
          <button
            onClick={() => setMotorSpeed(motorId, motorSpeeds[motorId-1])}
            disabled={!isConnected}
            className="bg-blue-500 hover:bg-blue-600 text-white px-2 py-1 rounded disabled:bg-gray-400 disabled:cursor-not-allowed">
            Set
          </button>
          <div>
            <span className="font-mono">
              {rpmValues[motorId]?.toFixed(2) || "0.00"} RPM
            </span>
          </div>
        </div>
      ))}
      
      <button
        onClick={emergencyStop}
        disabled={!isConnected}
        className="mt-4 bg-red-600 hover:bg-red-700 text-white py-2 px-4 rounded font-bold disabled:bg-red-400 disabled:cursor-not-allowed">
        EMERGENCY STOP
      </button>
    </div>
  );
};

export default RobotControlWidget;