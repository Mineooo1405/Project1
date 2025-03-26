import { Subject, BehaviorSubject } from 'rxjs';
import { WS_CONFIG } from './WebSocketConfig';
import { ConnectionErrorHandler } from '../utils/ConnectionErrorHandler';
import { convertBNO055ToIMU, convertEncoderValues, IMUData, EncoderData } from './Adapters';
import { robotIdHelper } from '../utils/robotIdHelper';

export type WebSocketStatus = 'connected' | 'connecting' | 'disconnected' | 'error';

// Export lại interface để dùng ở component
export type { IMUData, EncoderData }; // Sử dụng "export type" cho interfaces
export { convertBNO055ToIMU, convertEncoderValues }; // Giữ nguyên cho functions

// Unified WebSocket Service
export class UnifiedWebSocketService {
  private connections: Map<string, {
    socket: WebSocket | null,
    status$: BehaviorSubject<WebSocketStatus>,
    pingTimer: NodeJS.Timeout | null,
    lastPongTime: number,
    messageHandlers: Map<string, Set<(data: any) => void>>,
    reconnecting: boolean
  }> = new Map();
  
  // Singleton instance
  private static instance: UnifiedWebSocketService;
  
  // Base URL
  private baseUrl: string;
  
  // Get singleton instance
  public static getInstance(): UnifiedWebSocketService {
    if (!UnifiedWebSocketService.instance) {
      UnifiedWebSocketService.instance = new UnifiedWebSocketService();
    }
    return UnifiedWebSocketService.instance;
  }
  
  private constructor() {
    this.baseUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.baseUrl += `//${window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host}`;
    
    // Initialize standard endpoints
    this.initializeEndpoint(WS_CONFIG.ENDPOINTS.SERVER);
    
    // Register window beforeunload to close all connections gracefully
    window.addEventListener('beforeunload', () => this.closeAll());
  }
  
  // Initialize a new endpoint connection
  private initializeEndpoint(endpoint: string) {
    if (!this.connections.has(endpoint)) {
      this.connections.set(endpoint, {
        socket: null,
        status$: new BehaviorSubject<WebSocketStatus>('disconnected'),
        pingTimer: null,
        lastPongTime: Date.now(),
        messageHandlers: new Map(),
        reconnecting: false
      });
    }
    return this.connections.get(endpoint)!;
  }
  
  // Get full WebSocket URL
  private getUrl(endpoint: string): string {
    return `${this.baseUrl}${endpoint}`;
  }
  
  // Thêm kiểm tra trạng thái server trước khi kết nối nhiều endpoint
  private async checkServerAvailability(): Promise<boolean> {
    try {
      // Tạo một WebSocket connection test đến endpoint cơ bản
      return new Promise((resolve) => {
        const ws = new WebSocket(`ws://localhost:8000/ws/server`);
        const timeout = setTimeout(() => {
          ws.close();
          resolve(false);
        }, 3000);
        
        ws.onopen = () => {
          clearTimeout(timeout);
          ws.close();
          resolve(true);
        };
        
        ws.onerror = () => {
          clearTimeout(timeout);
          resolve(false);
        };
      });
    } catch (error) {
      console.error('Error checking server availability:', error);
      return false;
    }
  }
  
  // Connect to a specific endpoint
  public async connect(endpoint: string): Promise<void> {
    // Thêm kiểm tra trạng thái của server nếu chưa có kết nối nào
    if (this.connections.size === 0 || ![...this.connections.values()].some(c => 
        c.socket && c.socket.readyState === WebSocket.OPEN)) {
      const serverAvailable = await this.checkServerAvailability();
      if (!serverAvailable) {
        console.warn('WebSocket server unavailable. Delaying connection attempts.');
        
        // Đặt trạng thái lỗi nhưng không thử kết nối
        const connection = this.initializeEndpoint(endpoint);
        connection.status$.next('error');
        
        // Thực hiện lại sau 5 giây
        setTimeout(() => this.connect(endpoint), 5000);
        return;
      }
    }
    
    const connection = this.initializeEndpoint(endpoint);
    
    // Don't reconnect if already connected or connecting
    if (connection.socket && 
        (connection.socket.readyState === WebSocket.OPEN || 
         connection.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    
    // Update status to connecting
    connection.status$.next('connecting');
    
    try {
      const socket = new WebSocket(this.getUrl(endpoint));
      connection.socket = socket;
      
      socket.onopen = () => {
        console.log(`WebSocket connected to ${endpoint}`);
        connection.status$.next('connected');
        connection.reconnecting = false;
        
        // Start ping-pong
        this.startPing(endpoint);
      };
      
      socket.onclose = (event) => {
        console.log(`WebSocket disconnected from ${endpoint}: ${event.code} ${event.reason}`);
        
        // Clear ping timer
        if (connection.pingTimer) {
          clearInterval(connection.pingTimer);
          connection.pingTimer = null;
        }
        
        // Normal closure doesn't trigger reconnect
        if (event.code === 1000) {
          connection.status$.next('disconnected');
        } else {
          connection.status$.next('error');
          
          // Auto-reconnect if not manually disconnected
          if (!connection.reconnecting) {
            this.attemptReconnect(endpoint);
          }
        }
      };
      
      socket.onerror = (error) => {
        console.error(`WebSocket error on ${endpoint}:`, error);
        // Status will be updated by onclose
      };
      
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Handle pong message from server
          if (data.type === 'pong') {
            connection.lastPongTime = Date.now();
            return;
          }
          
          // Pre-process data for specific types
          let processedData = data;
          if (data.type === 'bno055_data' || data.type === 'imu_data') {
            processedData = convertBNO055ToIMU(data);
          } else if (data.type === 'encoder_data') {
            processedData = convertEncoderValues(data);
          }
          
          // Call all message handlers
          this.dispatchMessage(endpoint, '*', processedData);
          
          // Call specific message type handlers
          if (data.type) {
            this.dispatchMessage(endpoint, data.type, processedData);
          }
        } catch (error) {
          console.error(`Error parsing WebSocket message from ${endpoint}:`, error);
        }
      };
    } catch (error) {
      console.error(`Error connecting to WebSocket ${endpoint}:`, error);
      connection.status$.next('error');
      ConnectionErrorHandler.displayError(error, `connect-${endpoint}`);
    }
  }
  
  // Dispatch a message to registered handlers
  private dispatchMessage(endpoint: string, type: string, data: any) {
    const connection = this.connections.get(endpoint);
    if (!connection) return;
    
    const handlers = connection.messageHandlers.get(type);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error(`Error in message handler for ${endpoint} type ${type}:`, error);
        }
      });
    }
  }
  
  // Start ping-pong mechanism to keep connection alive
  private startPing(endpoint: string) {
    const connection = this.connections.get(endpoint);
    if (!connection) return;
    
    // Clear existing ping timer
    if (connection.pingTimer) {
      clearInterval(connection.pingTimer);
    }
    
    // Reset lastPongTime
    connection.lastPongTime = Date.now();
    
    // Start new ping timer
    connection.pingTimer = setInterval(() => {
      if (connection.socket?.readyState === WebSocket.OPEN) {
        try {
          // Send ping message
          connection.socket.send(JSON.stringify({
            type: 'ping',
            timestamp: Math.floor(Date.now() / 1000)
          }));
          
          // Check if we received pong responses
          const now = Date.now();
          if (now - connection.lastPongTime > WS_CONFIG.TIMEOUTS.PONG_TIMEOUT) {
            console.warn(`No pong response from ${endpoint} for ${WS_CONFIG.TIMEOUTS.PONG_TIMEOUT}ms`);
            
            // Force close and trigger reconnect
            connection.socket.close(4000, 'Pong timeout');
          }
        } catch (error) {
          console.error(`Error sending ping to ${endpoint}:`, error);
        }
      } else {
        // Clear timer if socket not open
        if (connection.pingTimer) {
          clearInterval(connection.pingTimer);
          connection.pingTimer = null;
        }
      }
    }, WS_CONFIG.TIMEOUTS.PING_INTERVAL);
  }
  
  // Attempt to reconnect to an endpoint
  private attemptReconnect(endpoint: string, attempt = 1) {
    const connection = this.connections.get(endpoint);
    if (!connection) return;
    
    // Prevent multiple reconnect attempts
    if (connection.reconnecting) return;
    connection.reconnecting = true;
    
    const maxAttempts = WS_CONFIG.TIMEOUTS.MAX_RECONNECT_ATTEMPTS;
    if (attempt <= maxAttempts) {
      const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
      console.log(`Attempting to reconnect to ${endpoint} in ${delay}ms (attempt ${attempt}/${maxAttempts})`);
      
      setTimeout(() => {
        // Lấy giá trị status hiện tại
        const currentStatus = connection.status$.value;
        
        // Kiểm tra nếu chưa kết nối
        if (currentStatus !== 'connected') {
          this.connect(endpoint);
          
          // SỬA: Sử dụng timeout để kiểm tra lại trạng thái sau khi connect
          // Thay vì kiểm tra ngay lập tức (TypeScript phát hiện điều này là vô nghĩa)
          setTimeout(() => {
            // Kiểm tra trạng thái sau khi đã thử kết nối
            if (connection.status$.value !== 'connected') {
              this.attemptReconnect(endpoint, attempt + 1);
            } else {
              connection.reconnecting = false;
            }
          }, 500); // Chờ 500ms để kết nối có cơ hội được thiết lập
        } else {
          connection.reconnecting = false;
        }
      }, delay);
    } else {
      console.error(`Failed to reconnect to ${endpoint} after ${maxAttempts} attempts`);
      connection.reconnecting = false;
      connection.status$.next('error');
    }
  }
  
  // Disconnect from an endpoint
  public disconnect(endpoint: string): void {
    const connection = this.connections.get(endpoint);
    if (!connection) return;
    
    // Clear ping timer
    if (connection.pingTimer) {
      clearInterval(connection.pingTimer);
      connection.pingTimer = null;
    }
    
    if (connection.socket && 
       (connection.socket.readyState === WebSocket.OPEN || 
        connection.socket.readyState === WebSocket.CONNECTING)) {
      
      try {
        // Send disconnect message first
        if (connection.socket.readyState === WebSocket.OPEN) {
          connection.socket.send(JSON.stringify({
            type: 'manual_disconnect',
            timestamp: Math.floor(Date.now() / 1000)
          }));
          
          // Wait a moment for the message to send
          setTimeout(() => {
            if (connection.socket) {
              connection.socket.close(1000, 'Manual disconnect');
              connection.socket = null;
            }
          }, 100);
        } else {
          // If still connecting, close immediately
          connection.socket.close(1000, 'Manual disconnect');
          connection.socket = null;
        }
      } catch (error) {
        console.error(`Error disconnecting from ${endpoint}:`, error);
        
        // Force close if there was an error
        if (connection.socket) {
          connection.socket.close(1000, 'Manual disconnect');
          connection.socket = null;
        }
      }
    }
    
    // Update status
    connection.status$.next('disconnected');
  }
  
  // Close all connections
  public closeAll(): void {
    this.connections.forEach((_, endpoint) => {
      this.disconnect(endpoint);
    });
  }
  
  // Send a message to an endpoint
  public sendMessage(endpoint: string, message: any): boolean {
    const connection = this.connections.get(endpoint);
    if (!connection || !connection.socket || connection.socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    
    try {
      const messageStr = typeof message === 'string' ? message : JSON.stringify(message);
      connection.socket.send(messageStr);
      return true;
    } catch (error) {
      console.error(`Error sending message to ${endpoint}:`, error);
      return false;
    }
  }
  
  // Get the current status of an endpoint
  public getStatus(endpoint: string): WebSocketStatus {
    const connection = this.connections.get(endpoint);
    return connection ? connection.status$.value : 'disconnected';
  }
  
  // Subscribe to status changes for an endpoint
  public onStatusChange(endpoint: string, callback: (status: WebSocketStatus) => void): () => void {
    const connection = this.initializeEndpoint(endpoint);
    
    const subscription = connection.status$.subscribe(callback);
    return () => subscription.unsubscribe();
  }
  
  // Subscribe to messages of a specific type
  public onMessage(endpoint: string, type: string, callback: (data: any) => void): () => void {
    const connection = this.initializeEndpoint(endpoint);
    
    if (!connection.messageHandlers.has(type)) {
      connection.messageHandlers.set(type, new Set());
    }
    
    connection.messageHandlers.get(type)!.add(callback);
    
    return () => {
      const handlers = connection.messageHandlers.get(type);
      if (handlers) {
        handlers.delete(callback);
      }
    };
  }
  
  // Check if an endpoint is connected
  public isConnected(endpoint: string): boolean {
    const connection = this.connections.get(endpoint);
    return connection?.status$.value === 'connected';
  }
  
  // Helper functions for common operations
  
  // Connect to a robot endpoint
  public connectToRobot(robotId: string): void {
    this.connect(WS_CONFIG.ENDPOINTS.ROBOT(robotId));
  }
  
  // Get robot encoder data
  public requestEncoderData(robotId: string): boolean {
    try {
      const endpoint = WS_CONFIG.ENDPOINTS.ENCODER(robotId);
      const formattedRobotId = robotIdHelper.formatForDb(robotId);
      
      if (isNaN(formattedRobotId)) {
        console.error(`Invalid robot ID format: ${robotId}`);
        return false;
      }
      
      return this.sendMessage(endpoint, {
        type: WS_CONFIG.MESSAGE_TYPES.GET_ENCODER,
        robot_id: formattedRobotId,
        timestamp: Math.floor(Date.now() / 1000)
      });
    } catch (error) {
      console.error(`Error requesting encoder data: ${error}`);
      return false;
    }
  }
  
  // Get robot IMU data
  public requestIMUData(robotId: string): boolean {
    try {
      const endpoint = WS_CONFIG.ENDPOINTS.IMU(robotId);
      const formattedRobotId = robotIdHelper.formatForDb(robotId);
      
      if (isNaN(formattedRobotId)) {
        console.error(`Invalid robot ID format: ${robotId}`);
        return false;
      }
      
      return this.sendMessage(endpoint, {
        type: WS_CONFIG.MESSAGE_TYPES.GET_IMU,
        robot_id: formattedRobotId,
        timestamp: Math.floor(Date.now() / 1000)
      });
    } catch (error) {
      console.error(`Error requesting IMU data: ${error}`);
      return false;
    }
  }
  
  // Send PID configuration
  public sendPIDConfig(robotId: string, motorId: number, pid: { kp: number, ki: number, kd: number }): boolean {
    try {
      const endpoint = WS_CONFIG.ENDPOINTS.PID(robotId);
      const formattedRobotId = robotIdHelper.formatForDb(robotId);
      
      if (isNaN(formattedRobotId)) {
        console.error(`Invalid robot ID format: ${robotId}`);
        return false;
      }
      
      return this.sendMessage(endpoint, {
        type: WS_CONFIG.MESSAGE_TYPES.SET_PID,
        robot_id: formattedRobotId,
        motor_id: motorId,
        kp: pid.kp,
        ki: pid.ki,
        kd: pid.kd,
        active: true,
        timestamp: Math.floor(Date.now() / 1000)
      });
    } catch (error) {
      console.error(`Error sending PID config: ${error}`);
      return false;
    }
  }
}

// Export the singleton instance
export const webSocketService = UnifiedWebSocketService.getInstance();

// Thêm ở cuối file
export default webSocketService; // Xuất mặc định singleton instance