import React, { useState, useEffect } from 'react';
import { useWebSocket, WebSocketEndpoint } from '../services/WebSocketManager';

// Danh sách các endpoint được hỗ trợ
const endpoints: WebSocketEndpoint[] = [
  '/ws/robot1',
  '/ws/robot2',
  '/ws/robot3',
  '/ws/robot4',
  '/ws/server'
];

const ConnectionStatusWidget: React.FC = () => {
  return (
    <div className="bg-gray-900 p-2 rounded-md">
      <h3 className="text-xs font-bold mb-2 text-white">WebSocket Connections</h3>
      <div className="space-y-1">
        {endpoints.map(endpoint => (
          <ConnectionStatus key={endpoint} endpoint={endpoint} />
        ))}
      </div>
    </div>
  );
};

const ConnectionStatus: React.FC<{ endpoint: WebSocketEndpoint }> = ({ endpoint }) => {
  // Sử dụng hook useWebSocket thay vì useWebSocketManager không tồn tại
  const { status, isConnected, connect, disconnect } = useWebSocket(endpoint, {
    autoConnect: false, // Không tự động kết nối
    onMessage: (data) => {
      // Xử lý tin nhắn nếu cần
    }
  });

  // Hiển thị tên ngắn gọn cho endpoint
  const displayName = endpoint.replace('/ws/', '');
  
  // Màu sắc dựa trên trạng thái
  const statusColor = 
    status === 'connected' ? 'bg-green-500' :
    status === 'connecting' ? 'bg-yellow-500' :
    status === 'error' ? 'bg-red-500' :
    'bg-gray-500';

  // Định dạng thời gian
  const formatTime = () => {
    return new Date().toLocaleTimeString();
  };
  
  return (
    <div className="flex items-center justify-between text-xs py-1 border-t border-gray-700">
      <div className="flex items-center">
        <div className={`w-2 h-2 rounded-full ${statusColor} mr-2`} />
        <span className="text-gray-300">{displayName}</span>
      </div>
      
      <div className="flex items-center gap-2">
        <span className="text-gray-400 text-xs">{status}</span>
        
        {!isConnected ? (
          <button
            onClick={connect}
            disabled={status === 'connecting'}
            className="px-1.5 py-0.5 rounded text-[10px] bg-blue-600 hover:bg-blue-700 text-white disabled:bg-gray-600"
          >
            Connect
          </button>
        ) : (
          <button
            onClick={disconnect}
            className="px-1.5 py-0.5 rounded text-[10px] bg-red-600 hover:bg-red-700 text-white"
          >
            Disconnect
          </button>
        )}
      </div>
    </div>
  );
};

export default ConnectionStatusWidget;