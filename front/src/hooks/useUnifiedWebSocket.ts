import { useState, useEffect, useCallback } from 'react';
import { webSocketService, WebSocketStatus } from '../services/WebSocketService';
import { useWebSocket as useOldWebSocket } from '../services/WebSocketManager';

// Hook tương thích với cả 2 hệ thống (cũ và mới)
export function useUnifiedWebSocket(
  endpoint: string,
  options: {
    autoConnect?: boolean;
    onMessage?: (data: any) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    onError?: (error: any) => void;
    useNewService?: boolean; // Flag để quyết định dùng service mới hay cũ
  } = {}
) {
  const {
    autoConnect = false,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    useNewService = true // Mặc định dùng service mới
  } = options;

  // Nếu dùng service mới
  if (useNewService) {
    const [status, setStatus] = useState<WebSocketStatus>(
      webSocketService.getStatus(endpoint)
    );
    const [isConnected, setIsConnected] = useState(
      webSocketService.isConnected(endpoint)
    );
    
    // Subscribe to status changes
    useEffect(() => {
      const unsubscribe = webSocketService.onStatusChange(endpoint, (newStatus) => {
        setStatus(newStatus);
        setIsConnected(newStatus === 'connected');
        
        // Call appropriate callbacks
        if (newStatus === 'connected') {
          onConnect?.();
        } else if (newStatus === 'disconnected') {
          onDisconnect?.();
        } else if (newStatus === 'error') {
          onError?.(new Error(`WebSocket ${endpoint} connection error`));
        }
      });
      
      return unsubscribe;
    }, [endpoint, onConnect, onDisconnect, onError]);
    
    // Subscribe to messages
    useEffect(() => {
      if (!onMessage) return;
      
      const unsubscribe = webSocketService.onMessage(endpoint, '*', onMessage);
      return unsubscribe;
    }, [endpoint, onMessage]);
    
    // Auto-connect if requested
    useEffect(() => {
      if (autoConnect) {
        webSocketService.connect(endpoint);
      }
    }, [autoConnect, endpoint]);
    
    // Connect function
    const connect = useCallback(() => {
      webSocketService.connect(endpoint);
    }, [endpoint]);
    
    // Disconnect function
    const disconnect = useCallback(() => {
      webSocketService.disconnect(endpoint);
    }, [endpoint]);
    
    // Send message function
    const sendMessage = useCallback((message: any) => {
      return webSocketService.sendMessage(endpoint, message);
    }, [endpoint]);
    
    return {
      status,
      isConnected,
      connect,
      disconnect,
      sendMessage
    };
  } 
  // Nếu dùng service cũ
  else {
    return useOldWebSocket(endpoint as any, options);
  }
}