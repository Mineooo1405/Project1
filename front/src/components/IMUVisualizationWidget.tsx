import React, { useState, useEffect } from 'react';
import { useWebSocket } from '../services/WebSocketManager';
import { RefreshCw, Play, Pause, RotateCcw, Download } from 'lucide-react';
import WidgetConnectionHeader from './WidgetConnectionHeader';
import { useRobotContext } from './RobotContext';
import { Line } from 'react-chartjs-2';
import 'chart.js/auto';
// Note: If chartjs-plugin-zoom is causing issues, you may need to install or remove it

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

const IMUVisualizationWidget: React.FC = () => {
  const { selectedRobotId } = useRobotContext();
  const imuSocketUrl = `/ws/${selectedRobotId}/imu`;

const { status, isConnected, connect, disconnect, sendMessage } = useWebSocket(imuSocketUrl as any, {
  autoConnect: false, // Start with false
  onMessage: (data) => handleWSMessage(data)
});

  // State for IMU data
  const [imuHistory, setImuHistory] = useState<{
    timestamps: string[];
    orientation: {
      roll: number[];
      pitch: number[];
      yaw: number[];
    };
    acceleration: {
      x: number[];
      y: number[];
      z: number[];
    };
    angular_velocity: {
      x: number[];
      y: number[];
      z: number[];
    };
  }>({
    timestamps: [],
    orientation: { roll: [], pitch: [], yaw: [] },
    acceleration: { x: [], y: [], z: [] },
    angular_velocity: { x: [], y: [], z: [] }
  });

  const [activeTab, setActiveTab] = useState<'orientation' | 'acceleration' | 'angular_velocity'>('orientation');
  const [liveUpdate, setLiveUpdate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Safe message handler that checks for null/undefined data
  const handleWSMessage = (data: any) => {
    if (!data) return;
    
    try {
      if (data.type === 'imu_data' || (data.type === 'initial_data' && data.imu)) {
        const imuData = data.type === 'imu_data' ? data : data.imu;
        
        if (!imuData) return;
        
        const timestamp = new Date().toLocaleTimeString();
        
        setImuHistory(prev => {
          // Limit data points to keep performance good
          const maxPoints = 100;
          const newTimestamps = [...prev.timestamps, timestamp];
          const sliceStart = newTimestamps.length > maxPoints ? newTimestamps.length - maxPoints : 0;
          
          return {
            timestamps: newTimestamps.slice(sliceStart),
            orientation: {
              roll: [...prev.orientation.roll, imuData.orientation?.roll || 0].slice(sliceStart),
              pitch: [...prev.orientation.pitch, imuData.orientation?.pitch || 0].slice(sliceStart),
              yaw: [...prev.orientation.yaw, imuData.orientation?.yaw || 0].slice(sliceStart)
            },
            acceleration: {
              x: [...prev.acceleration.x, imuData.acceleration?.x || 0].slice(sliceStart),
              y: [...prev.acceleration.y, imuData.acceleration?.y || 0].slice(sliceStart),
              z: [...prev.acceleration.z, imuData.acceleration?.z || 0].slice(sliceStart)
            },
            angular_velocity: {
              x: [...prev.angular_velocity.x, imuData.angular_velocity?.x || 0].slice(sliceStart),
              y: [...prev.angular_velocity.y, imuData.angular_velocity?.y || 0].slice(sliceStart),
              z: [...prev.angular_velocity.z, imuData.angular_velocity?.z || 0].slice(sliceStart)
            }
          };
        });
        
        setLoading(false);
      } else if (data.type === 'error') {
        setError(data.message || 'Unknown error occurred');
        setLoading(false);
      }
    } catch (e) {
      console.error("Error handling WebSocket message:", e);
      setError("Error processing data from server");
      setLoading(false);
    }
  };

  // Request IMU data from server
  const requestIMUData = () => {
    if (!isConnected) return;
    
    setLoading(true);
    sendMessage({
      type: 'get_imu_data'
    });
  };

  // Toggle live updates
  const toggleLiveUpdate = () => {
    setLiveUpdate(!liveUpdate);
  };

  // Clear history data
  const clearHistoryData = () => {
    setImuHistory({
      timestamps: [],
      orientation: { roll: [], pitch: [], yaw: [] },
      acceleration: { x: [], y: [], z: [] },
      angular_velocity: { x: [], y: [], z: [] }
    });
  };

  // Download data as CSV
  const downloadData = () => {
    if (imuHistory.timestamps.length === 0) return;
    
    let csvContent = 'timestamp,roll,pitch,yaw,accel_x,accel_y,accel_z,gyro_x,gyro_y,gyro_z\n';
    
    for (let i = 0; i < imuHistory.timestamps.length; i++) {
      csvContent += `${imuHistory.timestamps[i]},`;
      csvContent += `${imuHistory.orientation.roll[i] || 0},${imuHistory.orientation.pitch[i] || 0},${imuHistory.orientation.yaw[i] || 0},`;
      csvContent += `${imuHistory.acceleration.x[i] || 0},${imuHistory.acceleration.y[i] || 0},${imuHistory.acceleration.z[i] || 0},`;
      csvContent += `${imuHistory.angular_velocity.x[i] || 0},${imuHistory.angular_velocity.y[i] || 0},${imuHistory.angular_velocity.z[i] || 0}\n`;
    }
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `imu_data_${selectedRobotId}_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Effect for live updates
  useEffect(() => {
    let intervalId: number | null = null;
    
    if (liveUpdate && isConnected) {
      // Set regular polling when live update is enabled
      intervalId = window.setInterval(() => {
        requestIMUData();
      }, 500); 
    }
    
    // Cleanup on unmount or when dependencies change
    return () => {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
    };
  }, [liveUpdate, isConnected]); // Intentionally omitting requestIMUData to avoid dependency issues

  // Initial data request when connected
  useEffect(() => {
    if (isConnected) {
      requestIMUData();
      
      // Also subscribe/unsubscribe to IMU updates
      if (liveUpdate) {
        sendMessage({ type: 'subscribe_imu' });
      } else {
        sendMessage({ type: 'unsubscribe_imu' });
      }
    }
  }, [isConnected, liveUpdate]);

  // Chart data and options
  const getChartData = () => {
    switch (activeTab) {
      case 'orientation':
        return {
          labels: imuHistory.timestamps,
          datasets: [
            {
              label: 'Roll (rad)',
              data: imuHistory.orientation.roll,
              borderColor: 'rgba(255, 99, 132, 1)',
              backgroundColor: 'rgba(255, 99, 132, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Pitch (rad)',
              data: imuHistory.orientation.pitch,
              borderColor: 'rgba(54, 162, 235, 1)',
              backgroundColor: 'rgba(54, 162, 235, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Yaw (rad)',
              data: imuHistory.orientation.yaw,
              borderColor: 'rgba(75, 192, 192, 1)',
              backgroundColor: 'rgba(75, 192, 192, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            }
          ]
        };
      case 'acceleration':
        return {
          labels: imuHistory.timestamps,
          datasets: [
            {
              label: 'X (m/s²)',
              data: imuHistory.acceleration.x,
              borderColor: 'rgba(255, 99, 132, 1)',
              backgroundColor: 'rgba(255, 99, 132, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Y (m/s²)',
              data: imuHistory.acceleration.y,
              borderColor: 'rgba(54, 162, 235, 1)',
              backgroundColor: 'rgba(54, 162, 235, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Z (m/s²)',
              data: imuHistory.acceleration.z,
              borderColor: 'rgba(75, 192, 192, 1)',
              backgroundColor: 'rgba(75, 192, 192, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            }
          ]
        };
      case 'angular_velocity':
        return {
          labels: imuHistory.timestamps,
          datasets: [
            {
              label: 'X (rad/s)',
              data: imuHistory.angular_velocity.x,
              borderColor: 'rgba(255, 99, 132, 1)',
              backgroundColor: 'rgba(255, 99, 132, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Y (rad/s)',
              data: imuHistory.angular_velocity.y,
              borderColor: 'rgba(54, 162, 235, 1)',
              backgroundColor: 'rgba(54, 162, 235, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            },
            {
              label: 'Z (rad/s)',
              data: imuHistory.angular_velocity.z,
              borderColor: 'rgba(75, 192, 192, 1)',
              backgroundColor: 'rgba(75, 192, 192, 0.2)',
              tension: 0.4,
              pointRadius: 0,
            }
          ]
        };
      default:
        return {
          labels: [],
          datasets: []
        };
    }
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false as const,
    scales: {
      y: {
        beginAtZero: false
      },
      x: {
        ticks: {
          maxTicksLimit: 8
        }
      }
    },
    plugins: {
      legend: {
        position: 'top' as const,
      }
    },
  };

  // Get current values for display
  const getCurrentValues = () => {
    const lastIndex = imuHistory.timestamps.length - 1;
    
    return {
      orientation: {
        roll: imuHistory.orientation.roll[lastIndex] || 0,
        pitch: imuHistory.orientation.pitch[lastIndex] || 0,
        yaw: imuHistory.orientation.yaw[lastIndex] || 0
      },
      acceleration: {
        x: imuHistory.acceleration.x[lastIndex] || 0,
        y: imuHistory.acceleration.y[lastIndex] || 0,
        z: imuHistory.acceleration.z[lastIndex] || 0
      },
      angular_velocity: {
        x: imuHistory.angular_velocity.x[lastIndex] || 0,
        y: imuHistory.angular_velocity.y[lastIndex] || 0,
        z: imuHistory.angular_velocity.z[lastIndex] || 0
      }
    };
  };

  const currentValues = getCurrentValues();

  return (
    <div className="flex flex-col h-full">
      <WidgetConnectionHeader
        title="IMU Visualization"
        status={status}
        isConnected={isConnected}
        onConnect={connect}
        onDisconnect={disconnect}
      />

      {error && (
        <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-3 rounded mb-4">
          <p className="font-medium">Error</p>
          <p>{error}</p>
        </div>
      )}

      <div className="flex flex-col gap-4 p-4">
        {/* Controls */}
        <div className="flex justify-between items-center">
          <div className="flex space-x-2">
            <button
              onClick={() => setActiveTab('orientation')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium ${
                activeTab === 'orientation'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Orientation
            </button>
            <button
              onClick={() => setActiveTab('acceleration')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium ${
                activeTab === 'acceleration'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Acceleration
            </button>
            <button
              onClick={() => setActiveTab('angular_velocity')}
              className={`px-3 py-1.5 rounded-md text-sm font-medium ${
                activeTab === 'angular_velocity'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Angular Velocity
            </button>
          </div>
          
          <div className="flex space-x-2">
            <button
              onClick={requestIMUData}
              disabled={!isConnected || loading}
              className="p-1.5 rounded bg-blue-100 text-blue-700 hover:bg-blue-200 disabled:opacity-50"
              title="Refresh data"
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </button>
            
            <button
              onClick={toggleLiveUpdate}
              disabled={!isConnected}
              className={`p-1.5 rounded ${liveUpdate ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'} hover:bg-gray-200 disabled:opacity-50`}
              title={liveUpdate ? "Stop live updates" : "Start live updates"}
            >
              {liveUpdate ? <Pause size={16} /> : <Play size={16} />}
            </button>
            
            <button
              onClick={clearHistoryData}
              className="p-1.5 rounded bg-gray-100 text-gray-700 hover:bg-gray-200"
              title="Clear data"
            >
              <RotateCcw size={16} />
            </button>
            
            <button
              onClick={downloadData}
              disabled={imuHistory.timestamps.length === 0}
              className="p-1.5 rounded bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50"
              title="Download data as CSV"
            >
              <Download size={16} />
            </button>
          </div>
        </div>

        {/* Chart */}
        <div className="bg-white p-4 rounded-lg shadow border border-gray-200 h-[300px]">
          {imuHistory.timestamps.length > 0 ? (
            <Line data={getChartData()} options={chartOptions} />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              No data available. Click the refresh button or enable live updates.
            </div>
          )}
        </div>

        {/* Current Values */}
        <div className="bg-white p-4 rounded-lg shadow border border-gray-200">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Current Values</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="border rounded p-3">
              <h4 className="text-xs text-gray-500 mb-2">Orientation (rad)</h4>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm">Roll:</span>
                  <span className="text-sm font-mono">{currentValues.orientation.roll.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Pitch:</span>
                  <span className="text-sm font-mono">{currentValues.orientation.pitch.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Yaw:</span>
                  <span className="text-sm font-mono">{currentValues.orientation.yaw.toFixed(4)}</span>
                </div>
              </div>
            </div>
            
            <div className="border rounded p-3">
              <h4 className="text-xs text-gray-500 mb-2">Acceleration (m/s²)</h4>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm">X:</span>
                  <span className="text-sm font-mono">{currentValues.acceleration.x.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Y:</span>
                  <span className="text-sm font-mono">{currentValues.acceleration.y.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Z:</span>
                  <span className="text-sm font-mono">{currentValues.acceleration.z.toFixed(4)}</span>
                </div>
              </div>
            </div>
            
            <div className="border rounded p-3">
              <h4 className="text-xs text-gray-500 mb-2">Angular Velocity (rad/s)</h4>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm">X:</span>
                  <span className="text-sm font-mono">{currentValues.angular_velocity.x.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Y:</span>
                  <span className="text-sm font-mono">{currentValues.angular_velocity.y.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Z:</span>
                  <span className="text-sm font-mono">{currentValues.angular_velocity.z.toFixed(4)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IMUVisualizationWidget;