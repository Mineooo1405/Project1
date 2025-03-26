import React, { useState, useEffect } from 'react';
import { useUnifiedWebSocket } from '../hooks/useUnifiedWebSocket';
import { RefreshCw, Play, Pause, RotateCcw, Download } from 'lucide-react';
import WidgetConnectionHeader from './WidgetConnectionHeader';
import { useRobotContext } from './RobotContext';
import { Line } from 'react-chartjs-2';
import { convertEncoderValues } from '../services/Adapters';
import { WS_CONFIG } from '../services/WebSocketConfig';
import { robotIdHelper } from '../utils/robotIdHelper';

// Maximum history points
const MAX_HISTORY_POINTS = 100;

// Cập nhật interface để phản ánh đúng cấu trúc dữ liệu của EncoderData
interface EncoderData {
  rpm_1: number;  // Thay đổi từ 'values' sang các trường thực tế
  rpm_2: number;
  rpm_3: number;
  timestamp: string;
}

const EncoderDataWidget: React.FC = () => {
  const { selectedRobotId } = useRobotContext();
  // Sử dụng endpoint được cấu hình đúng
  const { status, isConnected, connect, disconnect, sendMessage } = 
    useUnifiedWebSocket(WS_CONFIG.ENDPOINTS.ENCODER(selectedRobotId), {
      autoConnect: false,
      onMessage: (data) => handleWSMessage(data),
      useNewService: true // Dùng service mới
    });

  // State
  const [encoderData, setEncoderData] = useState<EncoderData>({
    rpm_1: 0,
    rpm_2: 0,
    rpm_3: 0,
    timestamp: new Date().toISOString()
  });
  
  const [encoderHistory, setEncoderHistory] = useState({
    timestamps: [] as string[],
    encoder1: [] as number[],
    encoder2: [] as number[],
    encoder3: [] as number[]
  });
  
  const [rpmValues, setRpmValues] = useState([0, 0, 0]);
  const [liveUpdate, setLiveUpdate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Helper function to get time string
  const getTimeString = (): string => {
    const now = new Date();
    return now.toLocaleTimeString();
  };

  // Handle WebSocket messages
  const handleWSMessage = (data: any) => {
    try {
      setLoading(false);
      
      if (data.type === 'encoder_data' || data.type === 'encoder') {
        // Trích xuất dữ liệu từ định dạng mới
        const encoderValues = {
          rpm_1: data.rpm_1 || 0,
          rpm_2: data.rpm_2 || 0,
          rpm_3: data.rpm_3 || 0,
          timestamp: data.timestamp || new Date().toISOString()
        };
        
        // Cập nhật encoder data
        setEncoderData(encoderValues);
        
        // Tạo mảng RPM để sử dụng trong UI
        const rpmArray = [encoderValues.rpm_1, encoderValues.rpm_2, encoderValues.rpm_3];
        setRpmValues(rpmArray);
        
        // Cập nhật lịch sử
        setEncoderHistory(prev => {
          const newTimestamps = [...prev.timestamps, getTimeString()];
          const newEncoder1 = [...prev.encoder1, encoderValues.rpm_1];
          const newEncoder2 = [...prev.encoder2, encoderValues.rpm_2];
          const newEncoder3 = [...prev.encoder3, encoderValues.rpm_3];
          
          // Giới hạn số điểm
          if (newTimestamps.length > MAX_HISTORY_POINTS) {
            return {
              timestamps: newTimestamps.slice(-MAX_HISTORY_POINTS),
              encoder1: newEncoder1.slice(-MAX_HISTORY_POINTS),
              encoder2: newEncoder2.slice(-MAX_HISTORY_POINTS),
              encoder3: newEncoder3.slice(-MAX_HISTORY_POINTS)
            };
          }
          
          return {
            timestamps: newTimestamps,
            encoder1: newEncoder1,
            encoder2: newEncoder2,
            encoder3: newEncoder3
          };
        });
      } else if (data.type === 'error') {
        setError(data.message || "Đã xảy ra lỗi khi nhận dữ liệu encoder");
      }
    } catch (e) {
      console.error("Error handling WebSocket message:", e);
      setError("Lỗi xử lý dữ liệu: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  // Request encoder data
  const requestEncoderData = () => {
    if (!isConnected) return;
    
    setLoading(true);
    sendMessage({
      type: WS_CONFIG.MESSAGE_TYPES.GET_ENCODER,
      robot_id: robotIdHelper.formatForDb(selectedRobotId) // Đảm bảo ID đúng định dạng
    });
  };

  // Toggle live updates
  const toggleLiveUpdate = () => {
    const newLiveUpdate = !liveUpdate;
    setLiveUpdate(newLiveUpdate);
    
    if (isConnected) {
      sendMessage({
        type: newLiveUpdate ? 
          WS_CONFIG.MESSAGE_TYPES.SUBSCRIBE_ENCODER : 
          WS_CONFIG.MESSAGE_TYPES.UNSUBSCRIBE_ENCODER,
        robot_id: robotIdHelper.formatForDb(selectedRobotId)
      });
    }
  };

  // Reset history
  const clearHistory = () => {
    setEncoderHistory({
      timestamps: [],
      encoder1: [],
      encoder2: [],
      encoder3: []
    });
  };

  // Download data as CSV
  const downloadData = () => {
    if (encoderHistory.timestamps.length === 0) return;
    
    let csvContent = 'timestamp,encoder1,encoder2,encoder3,rpm1,rpm2,rpm3\n';
    
    for (let i = 0; i < encoderHistory.timestamps.length; i++) {
      csvContent += `${encoderHistory.timestamps[i]},`;
      csvContent += `${encoderHistory.encoder1[i] || 0},${encoderHistory.encoder2[i] || 0},${encoderHistory.encoder3[i] || 0},`;
      csvContent += `${(encoderHistory.encoder1[i] || 0) / 10},${(encoderHistory.encoder2[i] || 0) / 10},${(encoderHistory.encoder3[i] || 0) / 10}\n`;
    }
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `encoder_data_${selectedRobotId}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Live updates effect
  useEffect(() => {
    if (isConnected && liveUpdate) {
      const interval = setInterval(() => {
        requestEncoderData();
      }, 500);
      
      return () => clearInterval(interval);
    }
  }, [isConnected, liveUpdate]);

  // Initial data fetch when connected
  useEffect(() => {
    if (isConnected) {
      requestEncoderData();
    }
  }, [isConnected]);

  // Chart data
  const chartData = {
    labels: encoderHistory.timestamps,
    datasets: [
      {
        label: 'Encoder 1',
        data: encoderHistory.encoder1,
        borderColor: 'rgba(255, 99, 132, 1)',
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Encoder 2',
        data: encoderHistory.encoder2,
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        borderWidth: 2,
        pointRadius: 0,
      },
      {
        label: 'Encoder 3',
        data: encoderHistory.encoder3,
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
          text: 'Encoder Values'
        }
      }
    }
  };

  return (
    <div className="flex flex-col h-full p-4">
      <WidgetConnectionHeader
        title={`Encoder Data (${selectedRobotId})`}
        status={status}
        isConnected={isConnected}
        onConnect={connect}
        onDisconnect={disconnect}
      />
      
      <div className="flex gap-2 mb-4">
        <button
          onClick={requestEncoderData}
          disabled={!isConnected || loading}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700"
        >
          {loading ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          <span>Refresh</span>
        </button>
        
        <button
          onClick={toggleLiveUpdate}
          disabled={!isConnected}
          className={`px-3 py-1.5 rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed
                   ${liveUpdate 
                     ? 'bg-green-600 text-white hover:bg-green-700' 
                     : 'bg-gray-200 text-gray-800 hover:bg-gray-300'}`}
        >
          {liveUpdate ? (
            <>
              <Pause size={14} />
              <span>Live: ON</span>
            </>
          ) : (
            <>
              <Play size={14} />
              <span>Live: OFF</span>
            </>
          )}
        </button>
        
        <button
          onClick={clearHistory}
          className="px-3 py-1.5 bg-gray-200 text-gray-800 rounded-md flex items-center gap-1 hover:bg-gray-300"
        >
          <RotateCcw size={14} />
          <span>Clear</span>
        </button>
        
        <button
          onClick={downloadData}
          disabled={encoderHistory.timestamps.length === 0}
          className="px-3 py-1.5 bg-gray-200 text-gray-800 rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-300 ml-auto"
        >
          <Download size={14} />
          <span>CSV</span>
        </button>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-3 py-2 rounded mb-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="p-3 bg-blue-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 mb-1">Encoder 1</div>
          <div className="text-xl font-bold">{encoderData.rpm_1}</div>
          <div className="text-xs text-gray-500">Value</div>
          <div className="text-sm">{rpmValues[0].toFixed(1)} RPM</div>
        </div>
        <div className="p-3 bg-green-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 mb-1">Encoder 2</div>
          <div className="text-xl font-bold">{encoderData.rpm_2}</div>
          <div className="text-xs text-gray-500">Value</div>
          <div className="text-sm">{rpmValues[1].toFixed(1)} RPM</div>
        </div>
        <div className="p-3 bg-purple-50 rounded-lg text-center">
          <div className="text-xs text-gray-500 mb-1">Encoder 3</div>
          <div className="text-xl font-bold">{encoderData.rpm_3}</div>
          <div className="text-xs text-gray-500">Value</div>
          <div className="text-sm">{rpmValues[2].toFixed(1)} RPM</div>
        </div>
      </div>

      <div className="flex-grow" style={{ height: 'calc(100% - 200px)' }}>
        <Line data={chartData} options={chartOptions} />
      </div>
      
      <div className="mt-2 text-xs text-gray-500">
        Last updated: {new Date(encoderData.timestamp).toLocaleString()}
      </div>
    </div>
  );
};

export default EncoderDataWidget;