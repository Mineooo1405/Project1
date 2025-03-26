// Tạo file cấu hình tập trung cho WebSocket endpoints
export const WS_CONFIG = {
  BASE_URL: process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws',
  BRIDGE_URL: process.env.REACT_APP_WS_BRIDGE_URL || 'ws://localhost:8080',
  
  // Đảm bảo tất cả endpoint cần thiết đều được định nghĩa
  ENDPOINTS: {
    SERVER: 'ws://localhost:8000/ws/server',
    ROBOT: (robotId: string) => `ws://localhost:8000/ws/${robotId}`,
    IMU: (robotId: string) => `ws://localhost:8000/ws/${robotId}/imu`,
    PID: (robotId: string) => `ws://localhost:8000/ws/${robotId}/pid`,
    TRAJECTORY: (robotId: string) => `ws://localhost:8000/ws/${robotId}/trajectory`,
    ENCODER: (robotId: string) => `ws://localhost:8000/ws/${robotId}/encoder`,
    STATUS: (robotId: string) => `ws://localhost:8000/ws/${robotId}`,
    BNO055: (robotId: string) => `ws://localhost:8000/ws/${robotId}/bno055`,
  },
  
  // Message types cho API calls
  MESSAGE_TYPES: {
    GET_ENCODER: 'get_encoder_data',
    GET_IMU: 'get_bno055_data', // Thay đổi từ 'get_imu_data'
    SUBSCRIBE_IMU: 'subscribe_bno055', // Thay đổi từ 'subscribe_imu'
    UNSUBSCRIBE_IMU: 'unsubscribe_bno055', // Thay đổi từ 'unsubscribe_imu'
    SUBSCRIBE_ENCODER: 'subscribe_encoder',
    UNSUBSCRIBE_ENCODER: 'unsubscribe_encoder',
    SET_PID: 'set_pid_config',
    GET_PID: 'get_pid_config'
  },
  
  // Timeout settings
  TIMEOUTS: {
    PING_INTERVAL: 15000,
    PONG_TIMEOUT: 30000,
    RECONNECT_INTERVAL: 5000,
    MAX_RECONNECT_ATTEMPTS: 5
  }
};