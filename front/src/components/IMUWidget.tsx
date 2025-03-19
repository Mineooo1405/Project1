import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../services/WebSocketManager';
import { RefreshCw, RotateCw, RotateCcw, Play, Pause } from 'lucide-react';
import WidgetConnectionHeader from './WidgetConnectionHeader';
import { useRobotContext } from './RobotContext';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

// IMU data structure
interface IMUData {
  orientation: {
    roll: number;
    pitch: number;
    yaw: number;
  };
  acceleration: {
    x: number;
    y: number;
    z: number;
  };
  angular_velocity: {
    x: number;
    y: number;
    z: number;
  };
  timestamp: string;
}

// Maximum number of data points to keep for charts
const MAX_HISTORY_POINTS = 50;

const IMUWidget: React.FC = () => {
  const { selectedRobotId } = useRobotContext();
  const { status, isConnected, connect, disconnect, sendMessage } = useWebSocket(`/ws/${selectedRobotId}/imu` as any, {
    autoConnect: false,
    onMessage: (data) => handleWSMessage(data)
  });

  // State
  const [imuData, setImuData] = useState<IMUData>({
    orientation: { roll: 0, pitch: 0, yaw: 0 },
    acceleration: { x: 0, y: 0, z: 0 },
    angular_velocity: { x: 0, y: 0, z: 0 },
    timestamp: new Date().toISOString()
  });
  
  const [history, setHistory] = useState({
    timestamps: [] as string[],
    orientation: {
      roll: [] as number[],
      pitch: [] as number[],
      yaw: [] as number[]
    },
    acceleration: {
      x: [] as number[],
      y: [] as number[],
      z: [] as number[]
    },
    angular_velocity: {
      x: [] as number[],
      y: [] as number[],
      z: [] as number[]
    }
  });

  const [liveUpdate, setLiveUpdate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeChart, setActiveChart] = useState<'orientation' | 'acceleration' | 'angular_velocity'>('orientation');
  
  // 3D canvas for orientation visualization
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Handle WebSocket messages
  const handleWSMessage = (data: any) => {
    if (data.type === 'imu_data' || (data.type === 'initial_data' && data.imu)) {
      const imuData = data.type === 'imu_data' ? data : data.imu;
      
      // Update current IMU data
      setImuData({
        orientation: imuData.orientation || { roll: 0, pitch: 0, yaw: 0 },
        acceleration: imuData.acceleration || { x: 0, y: 0, z: 0 },
        angular_velocity: imuData.angular_velocity || { x: 0, y: 0, z: 0 },
        timestamp: imuData.timestamp || new Date().toISOString()
      });
      
      // Update history for charts
      setHistory(prev => {
        const timestamp = new Date().toLocaleTimeString();
        const newTimestamps = [...prev.timestamps, timestamp].slice(-MAX_HISTORY_POINTS);
        
        return {
          timestamps: newTimestamps,
          orientation: {
            roll: [...prev.orientation.roll, imuData.orientation?.roll || 0].slice(-MAX_HISTORY_POINTS),
            pitch: [...prev.orientation.pitch, imuData.orientation?.pitch || 0].slice(-MAX_HISTORY_POINTS),
            yaw: [...prev.orientation.yaw, imuData.orientation?.yaw || 0].slice(-MAX_HISTORY_POINTS)
          },
          acceleration: {
            x: [...prev.acceleration.x, imuData.acceleration?.x || 0].slice(-MAX_HISTORY_POINTS),
            y: [...prev.acceleration.y, imuData.acceleration?.y || 0].slice(-MAX_HISTORY_POINTS),
            z: [...prev.acceleration.z, imuData.acceleration?.z || 0].slice(-MAX_HISTORY_POINTS)
          },
          angular_velocity: {
            x: [...prev.angular_velocity.x, imuData.angular_velocity?.x || 0].slice(-MAX_HISTORY_POINTS),
            y: [...prev.angular_velocity.y, imuData.angular_velocity?.y || 0].slice(-MAX_HISTORY_POINTS),
            z: [...prev.angular_velocity.z, imuData.angular_velocity?.z || 0].slice(-MAX_HISTORY_POINTS)
          }
        };
      });
      
      setLoading(false);
      setError(null);
    } else if (data.type === 'error') {
      setError(data.message || 'Unknown error');
      setLoading(false);
    }
  };

  // Request IMU data from the server
  const requestIMUData = () => {
    if (!isConnected) return;
    
    setLoading(true);
    sendMessage({
      type: 'get_imu_data'
    });
  };

  // Toggle live updates
  const toggleLiveUpdate = () => {
    const newLiveUpdate = !liveUpdate;
    setLiveUpdate(newLiveUpdate);
    
    if (isConnected) {
      sendMessage({
        type: newLiveUpdate ? 'subscribe_imu' : 'unsubscribe_imu'
      });
    }
  };

  // Reset history data
  const clearHistory = () => {
    setHistory({
      timestamps: [],
      orientation: { roll: [], pitch: [], yaw: [] },
      acceleration: { x: [], y: [], z: [] },
      angular_velocity: { x: [], y: [], z: [] }
    });
  };

  // Live updates effect
  useEffect(() => {
    if (!isConnected || !liveUpdate) return;
    
    const interval = setInterval(() => {
      sendMessage({
        type: 'get_imu_data'
      });
    }, 500);
    
    return () => clearInterval(interval);
  }, [isConnected, liveUpdate, sendMessage]);

  // Initial data fetch when connected
  useEffect(() => {
    if (isConnected) {
      requestIMUData();
    }
  }, [isConnected]);

  // Render orientation visualization using canvas
  useEffect(() => {
    if (!canvasRef.current) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw orientation visualization - simplified representation
    const { roll, pitch, yaw } = imuData.orientation;
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 10;
    
    // Draw circle representing the horizon
    ctx.beginPath();
    ctx.ellipse(
      centerX, 
      centerY, 
      radius, 
      radius * Math.abs(Math.cos(pitch)), 
      yaw, 
      0, 
      2 * Math.PI
    );
    ctx.strokeStyle = 'rgba(0, 0, 255, 0.8)';
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // Draw roll indicator
    const rollX = centerX + radius * 0.8 * Math.cos(roll);
    const rollY = centerY + radius * 0.8 * Math.sin(roll);
    
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(rollX, rollY);
    ctx.strokeStyle = 'rgba(255, 0, 0, 0.8)';
    ctx.lineWidth = 3;
    ctx.stroke();
    
    // Draw pitch indicator
    const pitchX = centerX + radius * 0.6 * Math.sin(pitch);
    const pitchY = centerY - radius * 0.6 * Math.cos(pitch);
    
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(pitchX, pitchY);
    ctx.strokeStyle = 'rgba(0, 255, 0, 0.8)';
    ctx.lineWidth = 3;
    ctx.stroke();
    
    // Add labels
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.font = '12px Arial';
    ctx.fillText('Roll', rollX + 5, rollY + 5);
    ctx.fillText('Pitch', pitchX + 5, pitchY + 5);
    
    // Draw direction indicators
    ctx.font = '10px Arial';
    ctx.fillText('N', centerX, centerY - radius - 10);
    ctx.fillText('E', centerX + radius + 10, centerY);
    ctx.fillText('S', centerX, centerY + radius + 15);
    ctx.fillText('W', centerX - radius - 15, centerY);
    
  }, [imuData.orientation]);

  // Chart data for different modes
  const chartData = {
    labels: history.timestamps,
    datasets: activeChart === 'orientation' ? [
      {
        label: 'Roll',
        data: history.orientation.roll,
        borderColor: 'rgba(255, 99, 132, 1)',
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Pitch',
        data: history.orientation.pitch,
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Yaw',
        data: history.orientation.yaw,
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      }
    ] : activeChart === 'acceleration' ? [
      {
        label: 'X',
        data: history.acceleration.x,
        borderColor: 'rgba(255, 99, 132, 1)',
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Y',
        data: history.acceleration.y,
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Z',
        data: history.acceleration.z,
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      }
    ] : [
      {
        label: 'X',
        data: history.angular_velocity.x,
        borderColor: 'rgba(255, 99, 132, 1)',
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Y',
        data: history.angular_velocity.y,
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Z',
        data: history.angular_velocity.z,
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      }
    ]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 0 // Disable animations for better performance
    },
    scales: {
      x: {
        ticks: {
          maxTicksLimit: 5
        }
      },
      y: {
        title: {
          display: true,
          text: activeChart === 'orientation' 
            ? 'Rad' 
            : activeChart === 'acceleration' 
              ? 'm/s²' 
              : 'rad/s'
        }
      }
    },
    plugins: {
      title: {
        display: true,
        text: activeChart === 'orientation' 
          ? 'Orientation (Roll, Pitch, Yaw)' 
          : activeChart === 'acceleration' 
            ? 'Acceleration (X, Y, Z)' 
            : 'Angular Velocity (X, Y, Z)'
      },
      legend: {
        position: 'top' as const,
      },
    },
  };

  // Format angle to degrees
  const formatAngle = (rad: number) => {
    return (rad * 180 / Math.PI).toFixed(1) + '°';
  };

  return (
    <div className="flex flex-col h-full">
      <WidgetConnectionHeader
        title="IMU Data Visualization"
        status={status}
        isConnected={isConnected}
        onConnect={connect}
        onDisconnect={disconnect}
      />

      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-3 mb-4 rounded">
          <p className="font-medium">Lỗi</p>
          <p>{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        {/* IMU Orientation Visualization */}
        <div className="bg-white p-4 rounded-lg shadow border border-gray-200">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-medium">Orientation Visualization</h3>
            <button
              onClick={requestIMUData}
              disabled={!isConnected || loading}
              className="p-1.5 rounded bg-blue-100 text-blue-700 hover:bg-blue-200 disabled:opacity-50"
              title="Refresh IMU data"
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          <div className="aspect-square w-full mb-3 bg-gray-50 rounded-lg">
            <canvas ref={canvasRef} width={300} height={300} className="w-full h-full" />
          </div>

          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="p-2 bg-red-50 rounded">
              <div className="text-xs text-gray-500">Roll</div>
              <div className="font-bold">{formatAngle(imuData.orientation.roll)}</div>
            </div>
            <div className="p-2 bg-green-50 rounded">
              <div className="text-xs text-gray-500">Pitch</div>
              <div className="font-bold">{formatAngle(imuData.orientation.pitch)}</div>
            </div>
            <div className="p-2 bg-blue-50 rounded">
              <div className="text-xs text-gray-500">Yaw</div>
              <div className="font-bold">{formatAngle(imuData.orientation.yaw)}</div>
            </div>
          </div>
        </div>

        {/* Current IMU Data */}
        <div className="bg-white p-4 rounded-lg shadow border border-gray-200">
          <h3 className="font-medium mb-3">Current IMU Data</h3>
          
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-1">Acceleration (m/s²)</h4>
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 bg-gray-50 rounded">
                  <div className="text-xs text-gray-500">X-axis</div>
                  <div className="font-medium">{imuData.acceleration.x.toFixed(3)}</div>
                </div>
                <div className="p-2 bg-gray-50 rounded">
                  <div className="text-xs text-gray-500">Y-axis</div>
                  <div className="font-medium">{imuData.acceleration.y.toFixed(3)}</div>
                </div>
                <div className="p-2 bg-gray-50 rounded">
                  <div className="text-xs text-gray-500">Z-axis</div>
                  <div className="font-medium">{imuData.acceleration.z.toFixed(3)}</div>
                </div>
              </div>
            </div>
            
            <div>
              <h4 className="text-sm font-medium text-gray-500 mb-1">Angular Velocity (rad/s)</h4>
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 bg-gray-50 rounded">
                  <div className="text-xs text-gray-500">X-axis</div>
                  <div className="font-medium">{imuData.angular_velocity.x.toFixed(3)}</div>
                </div>
                <div className="p-2 bg-gray-50 rounded">
                  <div className="text-xs text-gray-500">Y-axis</div>
                  <div className="font-medium">{imuData.angular_velocity.y.toFixed(3)}</div>
                </div>
                <div className="p-2 bg-gray-50 rounded">
                  <div className="text-xs text-gray-500">Z-axis</div>
                  <div className="font-medium">{imuData.angular_velocity.z.toFixed(3)}</div>
                </div>
              </div>
            </div>

            <div className="text-xs text-gray-500 text-center">
              Last Updated: {new Date(imuData.timestamp).toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* History Chart */}
      <div className="bg-white p-4 rounded-lg shadow border border-gray-200">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-medium">IMU Data History</h3>
          <div className="flex gap-2">
            <button
              onClick={toggleLiveUpdate}
              className={`p-2 rounded-full ${liveUpdate 
                ? "bg-green-100 text-green-600 hover:bg-green-200" 
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
              title={liveUpdate ? "Disable live updates" : "Enable live updates"}
            >
              {liveUpdate ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <button
              onClick={clearHistory}
              className="p-2 bg-gray-100 text-gray-600 rounded-full hover:bg-gray-200"
              title="Clear history"
            >
              <RotateCcw size={16} />
            </button>
          </div>
        </div>
        
        <div className="mb-4 flex justify-center">
          <div className="inline-flex bg-gray-100 rounded-lg p-1">
            <button
              className={`px-3 py-1 rounded-md text-sm ${
                activeChart === 'orientation' 
                  ? 'bg-white shadow-sm' 
                  : 'text-gray-600 hover:bg-gray-200'
              }`}
              onClick={() => setActiveChart('orientation')}
            >
              Orientation
            </button>
            <button
              className={`px-3 py-1 rounded-md text-sm ${
                activeChart === 'acceleration' 
                  ? 'bg-white shadow-sm' 
                  : 'text-gray-600 hover:bg-gray-200'
              }`}
              onClick={() => setActiveChart('acceleration')}
            >
              Acceleration
            </button>
            <button
              className={`px-3 py-1 rounded-md text-sm ${
                activeChart === 'angular_velocity' 
                  ? 'bg-white shadow-sm' 
                  : 'text-gray-600 hover:bg-gray-200'
              }`}
              onClick={() => setActiveChart('angular_velocity')}
            >
              Angular Velocity
            </button>
          </div>
        </div>
        
        <div style={{ height: '250px' }}>
          {history.timestamps.length > 0 ? (
            <Line data={chartData} options={chartOptions} />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              No data available. Click the refresh button or enable live updates.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default IMUWidget;