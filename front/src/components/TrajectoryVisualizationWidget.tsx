import React, { useState, useEffect, useRef } from 'react';
import { useWebSocket } from '../services/WebSocketManager';
import { RefreshCw, Download, Trash2 } from 'lucide-react';
import WidgetConnectionHeader from './WidgetConnectionHeader';
import Chart from 'chart.js/auto';
import { useRobotContext } from './RobotContext';

const TrajectoryVisualizationWidget: React.FC = () => {
  const { selectedRobotId } = useRobotContext();
  const { status, isConnected, connect, disconnect, sendMessage } = useWebSocket(`/ws/${selectedRobotId}` as any, {
    autoConnect: false,
    onMessage: (data) => handleWSMessage(data)
  });

  const [trajectoryData, setTrajectoryData] = useState<{x: number[], y: number[]}>({
    x: [],
    y: []
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveUpdate, setLiveUpdate] = useState(false);
  const chartRef = useRef<HTMLCanvasElement>(null);
  const chartInstance = useRef<Chart | null>(null);

  const handleWSMessage = (data: any) => {
    if (data.type === 'trajectory_data' || (data.type === 'initial_data' && data.trajectory)) {
      const newData = data.type === 'trajectory_data' ? data : data.trajectory;
      
      setTrajectoryData(prev => {
        // For live updates, append data; otherwise replace it
        if (liveUpdate && data.type === 'trajectory_data') {
          return {
            x: [...prev.x, ...newData.x],
            y: [...prev.y, ...newData.y]
          };
        }
        return {
          x: newData.x || [],
          y: newData.y || []
        };
      });
      
      setLoading(false);
      setError(null);
    } else if (data.type === 'error') {
      setError(data.message || 'Unknown error');
      setLoading(false);
    }
  };

  const requestTrajectoryData = () => {
    if (!isConnected) return;
    
    setLoading(true);
    setError(null);
    
    sendMessage({
      type: 'get_trajectory'
    });
  };

  const clearTrajectory = () => {
    setTrajectoryData({ x: [], y: [] });
  };

  const toggleLiveUpdate = () => {
    const newLiveUpdate = !liveUpdate;
    setLiveUpdate(newLiveUpdate);
    
    if (newLiveUpdate && isConnected) {
      sendMessage({
        type: 'subscribe_trajectory'
      });
    } else if (isConnected) {
      sendMessage({
        type: 'unsubscribe_trajectory'
      });
    }
  };

  const downloadTrajectoryData = () => {
    if (!trajectoryData.x.length) return;

    const csvData = trajectoryData.x.map((x, i) => 
      `${x},${trajectoryData.y[i]}`
    ).join('\n');
    
    const blob = new Blob([`X,Y\n${csvData}`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `trajectory_${selectedRobotId}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Update chart when trajectory data changes
  useEffect(() => {
    if (!chartRef.current) return;
    
    if (chartInstance.current) {
      chartInstance.current.destroy();
    }
    
    const ctx = chartRef.current.getContext('2d');
    if (!ctx) return;
    
    chartInstance.current = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'Robot Trajectory',
          data: trajectoryData.x.map((x, i) => ({ x, y: trajectoryData.y[i] })),
          backgroundColor: 'rgb(54, 162, 235)',
          borderColor: 'rgb(54, 162, 235)',
          showLine: true,
          pointRadius: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: `Trajectory for ${selectedRobotId}`
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: 'X Position'
            }
          },
          y: {
            title: {
              display: true,
              text: 'Y Position'
            }
          }
        }
      }
    });
    
    return () => {
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }
    };
  }, [trajectoryData, selectedRobotId]);

  // Effect for switching robots
  useEffect(() => {
    // Reset data when robot changes
    setTrajectoryData({ x: [], y: [] });
    
    // Disconnect from previous endpoint
    disconnect();
    
    // Reset live update
    if (liveUpdate) {
      setLiveUpdate(false);
    }
  }, [selectedRobotId]);

  return (
    <div className="p-3 flex flex-col h-full">
      <WidgetConnectionHeader 
        title={`Trajectory (${selectedRobotId})`}
        status={status}
        isConnected={isConnected}
        onConnect={connect}
        onDisconnect={disconnect}
      />

      <div className="flex gap-2 mb-3">
        <button
          onClick={requestTrajectoryData}
          disabled={!isConnected || loading}
          className="px-3 py-1.5 bg-blue-600 text-white rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700"
        >
          {loading ? (
            <RefreshCw size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          <span>Fetch</span>
        </button>
        
        <button
          onClick={toggleLiveUpdate}
          disabled={!isConnected}
          className={`px-3 py-1.5 rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed
                     ${liveUpdate 
                       ? 'bg-green-600 text-white hover:bg-green-700' 
                       : 'bg-gray-200 text-gray-800 hover:bg-gray-300'}`}
        >
          <span>{liveUpdate ? 'Live: ON' : 'Live: OFF'}</span>
        </button>
        
        <button
          onClick={clearTrajectory}
          disabled={trajectoryData.x.length === 0}
          className="px-3 py-1.5 bg-red-600 text-white rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-red-700"
        >
          <Trash2 size={14} />
          <span>Clear</span>
        </button>
        
        <button
          onClick={downloadTrajectoryData}
          disabled={trajectoryData.x.length === 0}
          className="px-3 py-1.5 bg-green-600 text-white rounded-md flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-green-700 ml-auto"
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

      <div className="flex-grow relative min-h-[200px]">
        {trajectoryData.x.length > 0 || loading ? (
          <canvas ref={chartRef} className="w-full h-full" />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-gray-400 border border-dashed border-gray-300 rounded-md">
            No trajectory data available
          </div>
        )}
      </div>
      
      <div className="mt-2 text-xs text-gray-500">
        Points: {trajectoryData.x.length}
      </div>
    </div>
  );
};

export default TrajectoryVisualizationWidget;