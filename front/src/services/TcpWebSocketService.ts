import EventEmitter from 'events'; // Thêm import cho EventEmitter

type MessageHandler = (message: any) => void;
type ConnectionChangeCallback = (isConnected: boolean) => void;

export interface PIDValues {
  kp: number;
  ki: number;
  kd: number;
}

// Ví dụ cấu trúc của TcpWebSocketService
interface TcpWebSocketService {
  connect(): void;
  disconnect(): void;
  sendMessage(message: any): void;
  onMessage(type: string, callback: (data: any) => void): void;
  offMessage(type: string, callback: (data: any) => void): void;
  onConnectionChange(callback: (connected: boolean) => void): void;
  offConnectionChange(callback: (connected: boolean) => void): void;
}

class TcpWebSocketService {
  private ws: WebSocket | null = null;
  private isWsConnected: boolean = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private eventEmitter = new EventEmitter();
  private messageHandlers: Record<string, Set<MessageHandler>> = {}; // Sửa thành Set thay vì Function[]
  private url: string;

  constructor() {
    // Kết nối đến WebSocket Bridge thay vì FastAPI backend
    const hostname = window.location.hostname;
    this.url = `ws://${hostname}:9003`; // Loại bỏ /ws vì có thể là nguồn lỗi
    
    console.log(`TcpWebSocketService will connect to: ${this.url}`);
    this.connect(); // Tự động kết nối khi khởi tạo
  }

  private socket: WebSocket | null = null;
  private _isConnected: boolean = false;
  private reconnectInterval: number = 5000;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private connectionListeners: Array<ConnectionChangeCallback> = [];

  // Đảm bảo URL đúng cho WebSocket Bridge

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
      console.log(`Connecting to WebSocket at ${this.url}...`);
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        console.log('WebSocket connection established');
        this._isConnected = true;
        
        // Thông báo kết nối thành công
        this.notifyConnectionChange(true);
        
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
        this.reconnectAttempts = 0; // Reset số lần thử kết nối
      };

      this.socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleMessage(data);
        } catch (error) {
          console.error('Error processing message:', error);
        }
      };

      this.socket.onclose = () => {
        console.log('WebSocket connection closed');
        this._isConnected = false;
        
        // Thông báo ngắt kết nối
        this.notifyConnectionChange(false);
        
        // Thiết lập lại kết nối sau một khoảng thời gian
        this.attemptReconnect();
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        this._isConnected = false;
        
        // Thông báo lỗi kết nối
        this.notifyConnectionChange(false);
      };
    } catch (error) {
      console.error('Error connecting to WebSocket:', error);
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
        console.error('Error in connection listener:', error);
      }
    });
  }

  /**
   * Xử lý tin nhắn nhận được từ WebSocket
   */
  private handleMessage(data: any): void {
    // Xử lý tin nhắn chung
    console.log('📥 Received from TCP server:', data);
    
    // Gọi các handlers cho các loại tin nhắn cụ thể
    if (data.type && this.messageHandlers[data.type]) {
      const handlers = this.messageHandlers[data.type];
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error(`Error in handler for message type ${data.type}:`, error);
          }
        });
      }
    }
    
    // Gọi các handlers cho tất cả các tin nhắn
    if (this.messageHandlers['*']) {
      const handlers = this.messageHandlers['*'];
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(data);
          } catch (error) {
            console.error('Error in handler for all messages:', error);
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
      console.error('Cannot send message: Not connected to TCP server');
      return false;
    }
    
    try {
      // Đảm bảo có trường timestamp và frontend=true
      if (!message.timestamp) {
        message.timestamp = Date.now() / 1000;
      }
      if (!message.hasOwnProperty('frontend')) {
        message.frontend = true;  // Đánh dấu tin nhắn từ frontend
      }
      
      // Log thông điệp đang gửi
      console.log('📤 Sending to TCP server:', message);
      
      // Gửi dưới dạng JSON string
      this.socket.send(JSON.stringify(message));
      return true;
    } catch (error) {
      console.error('Error sending message to TCP server:', error);
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
      frontend: true,
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
      frontend: true,
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
      frontend: true,
      timestamp: Date.now() / 1000
    });
  }
  
  /**
   * Đăng ký handler cho loại thông điệp cụ thể
   */
  onMessage(type: string, handler: MessageHandler): void {
    if (!this.messageHandlers[type]) {
      this.messageHandlers[type] = new Set<MessageHandler>();
    }
    this.messageHandlers[type].add(handler);
  }
  
  /**
   * Hủy đăng ký handler
   */
  offMessage(type: string, handler: MessageHandler): void {
    const handlers = this.messageHandlers[type];
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
      console.log('Maximum reconnection attempts reached');
      return;
    }
    
    this.reconnectAttempts++;
    
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    this.reconnectTimer = setTimeout(() => {
      console.log('Reconnecting...');
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
const tcpWebSocketService = new TcpWebSocketService();

export default tcpWebSocketService;