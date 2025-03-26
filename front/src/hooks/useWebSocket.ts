import { useState, useEffect, useCallback, useRef } from 'react';
import { webSocketService, WebSocketStatus } from '../services/WebSocketService';

export function useWebSocket(
  endpoint: string,
  options: {
    autoConnect?: boolean;
    onMessage?: (data: any) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    onError?: (error: any) => void;
  } = {}
) {
  const {
    autoConnect = false,
    onMessage,
    onConnect,
    onDisconnect,
    onError
  } = options;
  
  const [status, setStatus] = useState<WebSocketStatus>(
    webSocketService.getStatus(endpoint)
  );
  const [isConnected, setIsConnected] = useState(
    webSocketService.isConnected(endpoint)
  );
  
  // Keep track of component mounted state
  const mountedRef = useRef(true);
  
  // Keep callback refs to avoid unnecessary re-renders
  const callbacksRef = useRef({ onMessage, onConnect, onDisconnect, onError });
  
  // Update callback refs when they change
  useEffect(() => {
    callbacksRef.current = { onMessage, onConnect, onDisconnect, onError };
  }, [onMessage, onConnect, onDisconnect, onError]);
  
  // Track mounted state
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);
  
  // Subscribe to status changes
  useEffect(() => {
    const unsubscribe = webSocketService.onStatusChange(endpoint, (newStatus) => {
      if (!mountedRef.current) return;
      
      setStatus(newStatus);
      setIsConnected(newStatus === 'connected');
      
      // Call appropriate callbacks
      if (newStatus === 'connected') {
        callbacksRef.current.onConnect?.();
      } else if (newStatus === 'disconnected') {
        callbacksRef.current.onDisconnect?.();
      } else if (newStatus === 'error') {
        callbacksRef.current.onError?.(new Error(`WebSocket ${endpoint} connection error`));
      }
    });
    
    return unsubscribe;
  }, [endpoint]);
  
  // Subscribe to messages
  useEffect(() => {
    if (!callbacksRef.current.onMessage) return;
    
    const unsubscribe = webSocketService.onMessage(endpoint, '*', (data) => {
      if (mountedRef.current) {
        callbacksRef.current.onMessage?.(data);
      }
    });
    
    return unsubscribe;
  }, [endpoint]);
  
  // Auto-connect if requested
  useEffect(() => {
    if (autoConnect) {
      webSocketService.connect(endpoint);
    }
    
    // Do NOT disconnect on unmount - let the component explicitly call disconnect
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