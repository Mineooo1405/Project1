import React, { useEffect, useRef, useState } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import './TrajectoryWidget.css';

const TrajectoryWidget = ({ robotId }) => {
  const canvasRef = useRef(null);
  const { sendMessage, lastMessage } = useWebSocket();
  const [trajectory, setTrajectory] = useState({
    currentPosition: { x: 0, y: 0, theta: 0 },
    points: { x: [0], y: [0], theta: [0] }
  });
  
  // Yêu cầu dữ liệu quỹ đạo ban đầu và thiết lập cập nhật định kỳ
  useEffect(() => {
    // Lấy quỹ đạo hiện tại khi component mount
    sendMessage({ type: 'get_trajectory', robot_id: robotId });
    
    // Thiết lập yêu cầu encoder data định kỳ (sẽ cập nhật quỹ đạo)
    const interval = setInterval(() => {
      sendMessage({ type: 'get_encoder_data', robot_id: robotId });
    }, 1000); // Cập nhật mỗi giây
    
    return () => clearInterval(interval);
  }, [robotId, sendMessage]);
  
  // Xử lý các tin nhắn từ WebSocket
  useEffect(() => {
    if (!lastMessage) return;
    
    try {
      const data = JSON.parse(lastMessage);
      
      // Xử lý dữ liệu quỹ đạo
      if (data.type === 'trajectory_data' || data.type === 'trajectory_update') {
        if (data.trajectory) {
          setTrajectory(data.trajectory);
        }
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  }, [lastMessage]);
  
  // Vẽ quỹ đạo lên canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas;
    
    // Xóa canvas
    ctx.clearRect(0, 0, width, height);
    
    // Thiết lập tỷ lệ và vị trí trung tâm
    const scale = 50; // pixels per meter
    const centerX = width / 2;
    const centerY = height / 2;
    
    // Vẽ lưới tham chiếu
    ctx.strokeStyle = '#ddd';
    ctx.lineWidth = 1;
    
    // Vẽ trục x, y
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(width, centerY);
    ctx.moveTo(centerX, 0);
    ctx.lineTo(centerX, height);
    ctx.stroke();
    
    // Không có điểm quỹ đạo, kết thúc ở đây
    if (!trajectory.points || !trajectory.points.x || trajectory.points.x.length === 0) {
      return;
    }
    
    // Vẽ đường quỹ đạo
    ctx.strokeStyle = '#2196F3';
    ctx.lineWidth = 2;
    ctx.beginPath();
    
    const { x, y } = trajectory.points;
    for (let i = 0; i < x.length; i++) {
      const canvasX = centerX + x[i] * scale;
      const canvasY = centerY - y[i] * scale; // Đảo ngược y vì trục y của canvas hướng xuống
      
      if (i === 0) {
        ctx.moveTo(canvasX, canvasY);
      } else {
        ctx.lineTo(canvasX, canvasY);
      }
    }
    ctx.stroke();
    
    // Vẽ các điểm dọc theo quỹ đạo
    ctx.fillStyle = '#4CAF50';
    for (let i = 0; i < x.length; i += 5) { // Vẽ mỗi 5 điểm để giảm số lượng
      const canvasX = centerX + x[i] * scale;
      const canvasY = centerY - y[i] * scale;
      
      ctx.beginPath();
      ctx.arc(canvasX, canvasY, 2, 0, 2 * Math.PI);
      ctx.fill();
    }
    
    // Vẽ vị trí robot hiện tại
    const currentX = centerX + trajectory.currentPosition.x * scale;
    const currentY = centerY - trajectory.currentPosition.y * scale;
    const currentTheta = trajectory.currentPosition.theta;
    
    // Vẽ hình tròn đại diện cho robot
    ctx.fillStyle = '#FF5722';
    ctx.beginPath();
    ctx.arc(currentX, currentY, 8, 0, 2 * Math.PI);
    ctx.fill();
    
    // Vẽ đường chỉ hướng
    ctx.strokeStyle = '#FF5722';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(currentX, currentY);
    ctx.lineTo(
      currentX + 15 * Math.cos(currentTheta),
      currentY - 15 * Math.sin(currentTheta)
    );
    ctx.stroke();
    
    // Hiển thị tọa độ hiện tại
    ctx.fillStyle = '#000';
    ctx.font = '12px Arial';
    ctx.fillText(
      `(${trajectory.currentPosition.x.toFixed(2)}, ${trajectory.currentPosition.y.toFixed(2)}, ${trajectory.currentPosition.theta.toFixed(2)} rad)`,
      10,
      20
    );
    
  }, [trajectory]);
  
  return (
    <div className="trajectory-widget">
      <div className="trajectory-header">
        <h3>Quỹ đạo Robot</h3>
        <div className="position-info">
          <span>X: {trajectory.currentPosition.x.toFixed(2)} m</span>
          <span>Y: {trajectory.currentPosition.y.toFixed(2)} m</span>
          <span>θ: {trajectory.currentPosition.theta.toFixed(2)} rad</span>
        </div>
      </div>
      <div className="trajectory-canvas-container">
        <canvas
          ref={canvasRef}
          width={400}
          height={400}
          className="trajectory-canvas"
        />
      </div>
      <div className="trajectory-controls">
        <button onClick={() => sendMessage({ 
          type: 'reset_position', 
          robot_id: robotId 
        })}>
          Đặt lại vị trí
        </button>
      </div>
    </div>
  );
};

export default TrajectoryWidget;