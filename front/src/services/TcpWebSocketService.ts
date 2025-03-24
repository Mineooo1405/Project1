/**
 * TCP WebSocket Service
 * Bổ sung hàm onConnectionChange để theo dõi trạng thái kết nối
 */

type MessageHandler = (message: any) => void;
type ConnectionChangeCallback = (isConnected: boolean) => void;

export interface PIDValues {
  kp: number;
  ki: number;
  kd: number;
}

class TcpWebSocketService {
  private socket: WebSocket | null = null;
  private url: string;
  private _isConnected: boolean = false;
  private reconnectInterval: number = 5000;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private messageHandlers: Map<string, Set<MessageHandler>> = new Map();
  private connectionListeners: Array<ConnectionChangeCallback> = [];

  constructor(url: string) {
    this.url = url;
    this.connect();
  }

  /**
   * Đăng ký lắng nghe sự thay đổi trạng thái kết nối
   */
  public onConnectionChange(callback: ConnectionChangeCallback): void {
    this.connectionListeners.push(callback);
    // Gọi callback ngay lập tức với trạng thái hiện tại
    if (callback && typeof callback === 'function') {
      callback(this._isConnected);
    }
  }

  /**
   * Hủy đăng ký lắng nghe sự thay đổi trạng thái kết nối
   */
  public offConnectionChange(callback: ConnectionChangeCallback): void {
    this.connectionListeners = this.connectionListeners.filter(
      (listener) => listener !== callback
    );
  }

  /**
   * Thiết lập kết nối WebSocket
   */
  public connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)) {
      return;
    }

    try {
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        console.log('Kết nối WebSocket đã được thiết lập');
        this._isConnected = true;
        
        // Thông báo kết nối thành công
        this.notifyConnectionChange(true);
        
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleMessage(data);
        } catch (error) {
          console.error('Lỗi xử lý tin nhắn:', error);
        }
      };

      this.socket.onclose = () => {
        console.log('Kết nối WebSocket đã đóng');
        this._isConnected = false;
        
        // Thông báo ngắt kết nối
        this.notifyConnectionChange(false);
        
        // Thiết lập lại kết nối sau một khoảng thời gian
        this.attemptReconnect();
      };

      this.socket.onerror = (error) => {
        console.error('Lỗi WebSocket:', error);
        this._isConnected = false;
        
        // Thông báo lỗi kết nối
        this.notifyConnectionChange(false);
      };
    } catch (error) {
      console.error('Lỗi kết nối WebSocket:', error);
      this._isConnected = false;
      
      // Thông báo lỗi kết nối
      this.notifyConnectionChange(false);
    }
  }

  /**
   * Gửi thông báo khi trạng thái kết nối thay đổi
   */
  private notifyConnectionChange(isConnected: boolean): void {
    this.connectionListeners.forEach((listener) => {
      try {
        listener(isConnected);
      } catch (error) {
        console.error('Lỗi trong listener kết nối:', error);
      }
    });
  }

  /**
   * Xử lý tin nhắn nhận được từ WebSocket
   */
  private handleMessage(data: any): void {
    // Xử lý tin nhắn chung
    console.log('📥 Nhận từ TCP server:', data);
    
    // Gọi các handlers cho các loại tin nhắn cụ thể
    if (data.type && this.messageHandlers.has(data.type)) {
      const handlers = this.messageHandlers.get(data.type);
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error(`Lỗi trong handler cho tin nhắn loại ${data.type}:`, error);
          }
        });
      }
    }
    
    // Gọi các handlers cho tất cả các tin nhắn
    if (this.messageHandlers.has('*')) {
      const handlers = this.messageHandlers.get('*');
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error('Lỗi trong handler cho tất cả tin nhắn:', error);
          }
        });
      }
    }
  }

  /**
   * Gửi thông điệp đến TCP server
   */
  sendMessage(message: any): boolean {
    if (!this._isConnected || !this.socket) {
      console.error('Không thể gửi thông điệp: Chưa kết nối đến TCP server');
      return false;
    }
    
    try {
      // Đảm bảo có trường timestamp
      if (!message.timestamp) {
        message.timestamp = Date.now() / 1000;
      }
      
      // Log thông điệp đang gửi
      console.log('📤 Gửi đến TCP server:', message);
      
      // Gửi dưới dạng JSON string
      this.socket.send(JSON.stringify(message));
      return true;
    } catch (error) {
      console.error('Lỗi gửi thông điệp đến TCP server:', error);
      return false;
    }
  }
  
  /**
   * Gửi cấu hình PID
   */
  sendPidConfig(robotId: string, motorId: number, parameters: PIDValues): boolean {
    return this.sendMessage({
      type: "pid_config",
      robot_id: robotId,
      motor_id: motorId,
      parameters: parameters,
      timestamp: Date.now() / 1000
    });
  }
  
  /**
   * Lấy danh sách kết nối robot
   */
  getRobotConnections(): boolean {
    return this.sendMessage({
      type: "get_robot_connections",
      robot_id: "robot1", // Thêm robot_id mặc định
      timestamp: Date.now() / 1000
    });
  }
  
  /**
   * Giả lập kết nối robot đến TCP
   */
  simulateRobotConnection(robotId: string): boolean {
    return this.sendMessage({
      type: "connect_robot_simulator",
      robot_id: robotId,
      timestamp: Date.now() / 1000
    });
  }
  
  /**
   * Đăng ký handler cho loại thông điệp cụ thể
   */
  onMessage(type: string, handler: MessageHandler): void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, new Set());
    }
    this.messageHandlers.get(type)!.add(handler);
  }
  
  /**
   * Hủy đăng ký handler
   */
  offMessage(type: string, handler: MessageHandler): void {
    const handlers = this.messageHandlers.get(type);
    if (handlers) {
      handlers.delete(handler);
    }
  }
  
  /**
   * Ngắt kết nối
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
      this._isConnected = false;
      this.notifyConnectionChange(false);
    }
    
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
  
  /**
   * Thử kết nối lại
   */
  private attemptReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Đã đạt số lần thử kết nối lại tối đa');
      return;
    }
    
    this.reconnectAttempts++;
    
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    console.log(`Thử kết nối lại sau ${delay}ms (lần thử ${this.reconnectAttempts})`);
    
    this.reconnectTimer = setTimeout(() => {
      console.log('Đang kết nối lại...');
      this.connect();
    }, delay);
  }
  
  /**
   * Kiểm tra trạng thái kết nối
   */
  isConnected(): boolean {
    return this._isConnected;
  }

  /**
   * Getter cho trạng thái kết nối WebSocket
   */
  public isWebSocketConnected(): boolean {
    return this._isConnected;
  }
}

// Tạo instance singleton
const tcpWebSocketService = new TcpWebSocketService(process.env.REACT_APP_TCP_WS_URL || 'ws://localhost:9002');

export default tcpWebSocketService;