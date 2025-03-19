import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';

// Định nghĩa các type
export type WebSocketEndpoint = '/ws/robot1' | '/ws/robot2' | '/ws/robot3' | '/ws/robot4' | '/ws/server';
export type WebSocketStatus = 'connected' | 'disconnected' | 'connecting' | 'error';

// Constants
const PING_INTERVAL = 15000; // 15 giây
const PONG_TIMEOUT = 30000;  // 30 giây

// Tạo và quản lý singleton WebSocket
const createSocketManager = () => {
  // Khởi tạo đối tượng quản lý cho mỗi endpoint
  const sockets: Record<WebSocketEndpoint, {
    socket: WebSocket | null,
    listeners: Set<(data: any) => void>,
    pingTimer: NodeJS.Timeout | null,
    lastPongTime: number,
  }> = {
    '/ws/robot1': { socket: null, listeners: new Set(), pingTimer: null, lastPongTime: 0 },
    '/ws/robot2': { socket: null, listeners: new Set(), pingTimer: null, lastPongTime: 0 },
    '/ws/robot3': { socket: null, listeners: new Set(), pingTimer: null, lastPongTime: 0 },
    '/ws/robot4': { socket: null, listeners: new Set(), pingTimer: null, lastPongTime: 0 },
    '/ws/server': { socket: null, listeners: new Set(), pingTimer: null, lastPongTime: 0 }
  };

  return {
    sockets,
    
    // Lấy WebSocket URL
    getUrl(endpoint: WebSocketEndpoint): string {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${protocol}//${window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host}${endpoint}`;
    },
    
    // Đóng tất cả các kết nối
    closeAll() {
      Object.entries(this.sockets).forEach(([endpoint, data]) => {
        this.disconnect(endpoint as WebSocketEndpoint);
      });
    },
    
    // Ngắt kết nối một endpoint cụ thể
    disconnect(endpoint: WebSocketEndpoint) {
      const socket = this.sockets[endpoint];
      
      // Xóa timer ping nếu có
      if (socket.pingTimer) {
        clearInterval(socket.pingTimer);
        socket.pingTimer = null;
      }
      
      // Đóng kết nối với thông báo manual_disconnect
      if (socket.socket && 
          (socket.socket.readyState === WebSocket.OPEN)) {
        try {
          // Gửi thông báo ngắt kết nối thủ công để server có thể xử lý đúng
          socket.socket.send(JSON.stringify({
            type: 'manual_disconnect',
            timestamp: Date.now()
          }));
          
          // Đợi một chút để tin nhắn được gửi đi
          setTimeout(() => {
            if (socket.socket) {
              socket.socket.close(1000, "Manual disconnect");
              socket.socket = null;
            }
          }, 100);
        } catch (e) {
          // Nếu gửi tin nhắn thất bại, đóng kết nối ngay lập tức
          if (socket.socket) {
            socket.socket.close(1000, "Manual disconnect");
            socket.socket = null;
          }
        }
      } else if (socket.socket && socket.socket.readyState === WebSocket.CONNECTING) {
        // Nếu đang kết nối, đóng ngay
        socket.socket.close(1000, "Manual disconnect");
        socket.socket = null;
      }
    },
    
    // Bắt đầu gửi ping để giữ kết nối
    startPing(endpoint: WebSocketEndpoint) {
      const socket = this.sockets[endpoint];
      
      // Xóa timer cũ nếu có
      if (socket.pingTimer) {
        clearInterval(socket.pingTimer);
      }
      
      // Thiết lập thời gian pong cuối cùng
      socket.lastPongTime = Date.now();
      
      // Tạo timer mới
      socket.pingTimer = setInterval(() => {
        if (socket.socket?.readyState === WebSocket.OPEN) {
          // Gửi tin nhắn ping
          try {
            socket.socket.send(JSON.stringify({ 
              type: 'ping', 
              timestamp: Date.now() 
            }));
            
            // Kiểm tra timeout
            const now = Date.now();
            if (now - socket.lastPongTime > PONG_TIMEOUT) {
              console.warn(`No pong received for ${PONG_TIMEOUT}ms from ${endpoint}`);
              // KHÔNG tự động đóng kết nối, chỉ ghi log cảnh báo
            }
          } catch (e) {
            console.error(`Error sending ping to ${endpoint}:`, e);
            // KHÔNG tự động đóng kết nối, chỉ ghi log lỗi
          }
        } else {
          // Xóa timer nếu socket không còn mở
          if (socket.pingTimer) {
            clearInterval(socket.pingTimer);
            socket.pingTimer = null;
          }
        }
      }, PING_INTERVAL);
    }
  };
};

// Tạo singleton manager
const socketManager = createSocketManager();

// Context cho WebSocket
type WebSocketContextType = {
  connect: (endpoint: WebSocketEndpoint) => void;
  disconnect: (endpoint: WebSocketEndpoint) => void;
  send: (endpoint: WebSocketEndpoint, data: any) => boolean;
  status: Record<WebSocketEndpoint, WebSocketStatus>;
  subscribe: (endpoint: WebSocketEndpoint, listener: (data: any) => void) => () => void;
};

const WebSocketContext = createContext<WebSocketContextType | null>(null);

// Provider Component
export const WebSocketProvider: React.FC<{children: React.ReactNode}> = ({ children }) => {
  // State cho trạng thái kết nối - sử dụng useRef để tránh re-render không cần thiết
  const statusRef = useRef<Record<WebSocketEndpoint, WebSocketStatus>>({
    '/ws/robot1': 'disconnected',
    '/ws/robot2': 'disconnected',
    '/ws/robot3': 'disconnected',
    '/ws/robot4': 'disconnected',
    '/ws/server': 'disconnected',
  });
  
  // State cho UI - chỉ cập nhật khi có thay đổi thực sự
  const [status, setStatus] = useState(statusRef.current);

  // Kết nối tới endpoint - CHỈ KHI NGƯỜI DÙNG YÊU CẦU
  const connect = useCallback((endpoint: WebSocketEndpoint) => {
    const socketData = socketManager.sockets[endpoint];
    
    // Tránh kết nối trùng lắp
    if (socketData.socket && 
       (socketData.socket.readyState === WebSocket.OPEN || 
        socketData.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    
    // Cập nhật trạng thái nội bộ trước, sau đó UI
    statusRef.current = {
      ...statusRef.current,
      [endpoint]: 'connecting'
    };
    setStatus({ ...statusRef.current });
  
    // Tạo kết nối mới
    try {
      const url = socketManager.getUrl(endpoint);
      const ws = new WebSocket(url);
      
      // Lưu socket
      socketData.socket = ws;
      
      // Thiết lập handlers
      ws.onopen = () => {
        // Log và cập nhật trạng thái
        console.log(`Đã kết nối tới ${endpoint}`);
        
        // Cập nhật trạng thái nội bộ trước
        statusRef.current = {
          ...statusRef.current,
          [endpoint]: 'connected'
        };
        // Sau đó cập nhật UI
        setStatus({ ...statusRef.current });
        
        // Bắt đầu gửi ping để giữ kết nối
        socketManager.startPing(endpoint);
      };
    
      ws.onclose = (event) => {
        console.log(`Đã ngắt kết nối khỏi ${endpoint} (${event.code}: ${event.reason || 'No reason'})`);
        
        // Reset socket reference
        socketData.socket = null;
        
        // Cập nhật trạng thái nội bộ
        statusRef.current = {
          ...statusRef.current,
          [endpoint]: event.code === 1000 ? 'disconnected' : 'error'
        };
        // Cập nhật UI
        setStatus({ ...statusRef.current });
      };
    
      ws.onerror = (event) => {
        console.error(`Lỗi WebSocket với ${endpoint}:`, event);
        // Không cập nhật trạng thái ở đây, để onclose xử lý
      };
    
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Xử lý tin nhắn pong từ server
          if (data.type === 'pong') {
            socketData.lastPongTime = Date.now();
            return;
          }
    
          // Thông báo cho tất cả listeners
          socketData.listeners.forEach(listener => {
            try {
              listener(data);
            } catch (e) {
              console.error(`Lỗi listener: ${e}`);
            }
          });
        } catch (e) {
          console.warn(`Lỗi phân tích JSON: ${e}`);
        }
      };
    } catch (e) {
      console.error(`Lỗi tạo WebSocket cho ${endpoint}: ${e}`);
      
      // Cập nhật trạng thái error trong ref nội bộ
      statusRef.current = {
        ...statusRef.current,
        [endpoint]: 'error'
      };
      // Cập nhật UI
      setStatus({ ...statusRef.current });
    }
  }, []);
  
  // Gửi tin nhắn
  const send = useCallback((endpoint: WebSocketEndpoint, data: any): boolean => {
    const socketData = socketManager.sockets[endpoint];
    if (!socketData.socket || socketData.socket.readyState !== WebSocket.OPEN) return false;
    
    try {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      socketData.socket.send(message);
      return true;
    } catch (e) {
      console.error(`Lỗi gửi tin nhắn tới ${endpoint}: ${e}`);
      return false;
    }
  }, []);
  
  // Subscribe vào các sự kiện WebSocket - KHÔNG tự động kết nối
  const subscribe = useCallback((
    endpoint: WebSocketEndpoint,
    listener: (data: any) => void
  ) => {
    // Add safety check
  if (!socketManager.sockets[endpoint]) {
    console.error(`Socket endpoint ${endpoint} not initialized`);
    socketManager.sockets[endpoint] = { socket: null, listeners: new Set(), pingTimer: null, lastPongTime: 0 };
  }

  // Now it's safe to access listeners
  socketManager.sockets[endpoint].listeners.add(listener);
  
  return () => {
    if (socketManager.sockets[endpoint]) {
      socketManager.sockets[endpoint].listeners.delete(listener);
    }
  };
}, []);

  // Ngắt kết nối - CHỈ KHI NGƯỜI DÙNG YÊU CẦU
  const disconnect = useCallback((endpoint: WebSocketEndpoint) => {
    // Gửi tin nhắn manual_disconnect và đóng kết nối
    socketManager.disconnect(endpoint);
    
    // Cập nhật trạng thái nội bộ
    statusRef.current = {
      ...statusRef.current,
      [endpoint]: 'disconnected'
    };
    // Cập nhật UI
    setStatus({ ...statusRef.current });
  }, []);

  // Đóng tất cả kết nối khi unload
  useEffect(() => {
    const handleBeforeUnload = () => socketManager.closeAll();
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, []);

  // Context value - tránh re-renders không cần thiết
  const contextValue = React.useMemo(() => ({
    connect,
    disconnect,
    send,
    status,
    subscribe
  }), [connect, disconnect, send, status, subscribe]);

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
};

// Hook để sử dụng WebSocket - DEFAULT autoConnect = FALSE
export function useWebSocket(
  endpoint: WebSocketEndpoint, 
  options: {
    autoConnect?: boolean;
    onMessage?: (data: any) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    onError?: (error: any) => void;
  } = {}
) {
  const {
    autoConnect = false, // KHÔNG tự động kết nối
    onMessage,
    onConnect,
    onDisconnect,
    onError
  } = options;
  
  const context = useContext(WebSocketContext);
  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [isConnected, setIsConnected] = useState(false);
  
  // Tham chiếu để theo dõi component mounted
  const mountedRef = useRef(true);
  
  // Lưu các callbacks vào refs để tránh re-renders
  const callbacksRef = useRef({ onMessage, onConnect, onDisconnect, onError });
  
  // Cập nhật refs khi callbacks thay đổi
  useEffect(() => {
    callbacksRef.current = { onMessage, onConnect, onDisconnect, onError };
  }, [onMessage, onConnect, onDisconnect, onError]);
  
  // Cleanup khi unmount
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);
  
  if (!context) {
    throw new Error('useWebSocket phải được sử dụng trong WebSocketProvider');
  }
  
  // Theo dõi thay đổi trạng thái từ context
  useEffect(() => {
    const currentStatus = context.status[endpoint];
    
    // Chỉ cập nhật nếu có thay đổi thực sự và component vẫn mounted
    if (status !== currentStatus && mountedRef.current) {
      setStatus(currentStatus);
      
      if (currentStatus === 'connected') {
        setIsConnected(true);
        callbacksRef.current.onConnect?.();
      } else if (currentStatus === 'disconnected') {
        setIsConnected(false);
        callbacksRef.current.onDisconnect?.();
      } else if (currentStatus === 'error') {
        setIsConnected(false);
        callbacksRef.current.onError?.(new Error('Lỗi kết nối'));
      }
    }
  }, [context.status, endpoint, status]);
  
  // Subscribe vào messages - KHÔNG tự động kết nối
  useEffect(() => {
    if (!callbacksRef.current.onMessage) return undefined;
    
    const unsubscribe = context.subscribe(endpoint, (data) => {
      if (mountedRef.current) {
        callbacksRef.current.onMessage?.(data);
      }
    });
    
    return unsubscribe;
  }, [context, endpoint]);
  
  // Kết nối tự động nếu được yêu cầu - CHỈ CHẠY MỘT LẦN
  useEffect(() => {
    let connectTimeout: NodeJS.Timeout | null = null;
    
    if (autoConnect) {
      // Sử dụng setTimeout để tránh vòng lặp cập nhật vô hạn
      connectTimeout = setTimeout(() => {
        if (mountedRef.current) {
          context.connect(endpoint);
        }
      }, 50);
    }
    
    // Cleanup: KHÔNG tự động ngắt kết nối khi component unmount
    return () => {
      if (connectTimeout) {
        clearTimeout(connectTimeout);
      }
      // Để người dùng tự ngắt kết nối thông qua nút
    };
  }, [autoConnect, context, endpoint]);
  
  // API cho component
  const connect = useCallback(() => {
    context.connect(endpoint);
  }, [context, endpoint]);
  
  const disconnect = useCallback(() => {
    context.disconnect(endpoint);
  }, [context, endpoint]);
  
  const sendMessage = useCallback((data: any) => {
    return context.send(endpoint, data);
  }, [context, endpoint]);
  
  return {
    status,
    isConnected,
    connect,
    disconnect,
    sendMessage
  };
}
//hook
export function useRobotWebSocket(robotId: string, options = {}) {
  // Đảm bảo robotId hợp lệ
  const validRobotIds = ['robot1', 'robot2', 'robot3', 'robot4'];
  const actualRobotId = validRobotIds.includes(robotId) ? robotId : 'robot1';
  
  // Chuyển đổi robotId thành endpoint
  const endpoint = `/ws/${actualRobotId}` as WebSocketEndpoint;
  
  // Sử dụng hook WebSocket cơ bản với autoConnect = false
  const wsConnection = useWebSocket(endpoint, {
    autoConnect: false,  // KHÔNG tự động kết nối
    ...options
  });
  
  return {
    ...wsConnection,
    robotId: actualRobotId,
    endpoint
  };
}