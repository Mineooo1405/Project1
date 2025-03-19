import React, { useEffect, useState } from 'react';
import { useRobotContext } from './RobotContext';
import { useRobotWebSocket } from '../services/WebSocketManager';

// Định nghĩa kiểu dữ liệu cho tin nhắn WebSocket
type StatusMessage = {
  type: string;
  battery?: number;
  charging?: boolean;
  [key: string]: any;
};

const StatusWidget: React.FC = () => {
  const { selectedRobotId } = useRobotContext();
  const [batteryLevel, setBatteryLevel] = useState<number>(100);
  const [isCharging, setIsCharging] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  
  // Sửa cách gọi useRobotWebSocket để phù hợp với phiên bản đơn giản hóa
  // Thay vì gọi với một object chứa robotId, gọi với robotId là tham số đầu tiên
  const { 
    status, 
    isConnected, 
    sendMessage 
  } = useRobotWebSocket(selectedRobotId, {
    autoConnect: true,
    onMessage: (data: StatusMessage) => {
      // Cập nhật trạng thái khi nhận được dữ liệu mới
      if (data.type === 'status_update') {
        if (data.battery !== undefined) {
          setBatteryLevel(data.battery);
        }
        if (data.charging !== undefined) {
          setIsCharging(data.charging);
        }
        setLastUpdated(new Date());
      }
    },
    onConnect: () => {
      // Yêu cầu trạng thái ngay khi kết nối
      sendMessage({ type: 'get_status' });
    },
    onDisconnect: () => {
      console.log('Disconnected from status WebSocket');
    },
    onError: () => {
      console.log('Error with status WebSocket connection');
    }
  });
  
  // Gửi yêu cầu cập nhật trạng thái định kỳ
  useEffect(() => {
    if (isConnected) {
      // Ban đầu đã yêu cầu trong onConnect, không cần gửi lại ở đây
      
      // Lấy trạng thái mỗi 10 giây
      const interval = setInterval(() => {
        sendMessage({ type: 'get_status' });
      }, 10000);
      
      return () => clearInterval(interval);
    }
  }, [isConnected, sendMessage]);
  
  // Phản ứng khi selectedRobotId thay đổi
  useEffect(() => {
    if (isConnected) {
      // Yêu cầu trạng thái mới khi chuyển robot
      sendMessage({ type: 'get_status' });
    }
  }, [selectedRobotId, isConnected, sendMessage]);
  
  // Định dạng thời gian cập nhật cuối
  const formatLastUpdated = () => {
    const now = new Date();
    const diff = now.getTime() - lastUpdated.getTime();
    
    if (diff < 60000) { // Dưới 1 phút
      return 'vừa xong';
    } else if (diff < 3600000) { // Dưới 1 giờ
      const minutes = Math.floor(diff / 60000);
      return `${minutes} phút trước`;
    } else {
      return lastUpdated.toLocaleTimeString();
    }
  };
  
  return (
    <div className="flex items-center space-x-4">
      {/* Trạng thái kết nối */}
      <div className="flex items-center">
        <div className={`w-3 h-3 rounded-full mr-1 ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
        <span className="text-sm font-medium">
          {isConnected ? 'Đã kết nối' : 'Ngắt kết nối'}
        </span>
      </div>
      
      {/* Trạng thái pin */}
      {isConnected && (
        <div className="flex items-center">
          <div className="relative w-8 h-4 bg-gray-200 border border-gray-300 rounded">
            <div 
              className={`absolute left-0 top-0 bottom-0 ${
                batteryLevel > 20 ? 'bg-green-500' : 'bg-red-500'
              }`}
              style={{ width: `${batteryLevel}%` }}
            ></div>
          </div>
          <span className="text-xs ml-1">{batteryLevel}%</span>
          {isCharging && (
            <span className="ml-1 text-yellow-500">
              ⚡
            </span>
          )}
        </div>
      )}
      
      {/* Thời gian cập nhật */}
      {isConnected && (
        <div className="text-xs text-gray-500">
          Cập nhật: {formatLastUpdated()}
        </div>
      )}
    </div>
  );
};

export default StatusWidget;