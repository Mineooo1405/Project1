import React, { useState } from 'react';
import { useWebSocket } from '../services/WebSocketManager';
import { RefreshCw, Power, Save, RotateCcw } from 'lucide-react';

const PIDControlWidget: React.FC = () => {
  const [pidValues, setPidValues] = useState({
    kp: 1.0,
    ki: 0.1,
    kd: 0.01
  });
  
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'success' | 'error'>('idle');
  
  const {
    status,
    isConnected,
    connect,
    disconnect,
    sendMessage
  } = useWebSocket('/ws/robot1', {
    autoConnect: false,
    onMessage: (data) => {
      if (data.type === 'pid_response') {
        if (data.action === 'save' && data.status === 'success') {
          setSaveStatus('success');
          setIsSaving(false);
          setTimeout(() => setSaveStatus('idle'), 3000);
        } else if (data.action === 'save' && data.status !== 'success') {
          setSaveStatus('error');
          setIsSaving(false);
          setTimeout(() => setSaveStatus('idle'), 3000);
        } else if (data.action === 'get_config') {
          // Update PID values if server sends them
          if (data.pid) {
            setPidValues({
              kp: data.pid.kp || pidValues.kp,
              ki: data.pid.ki || pidValues.ki,
              kd: data.pid.kd || pidValues.kd
            });
          }
        }
      }
    }
  });
  
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setPidValues(prev => ({
      ...prev,
      [name]: Number(value)
    }));
  };
  
  const handleSave = () => {
    if (!isConnected) return;
    
    setIsSaving(true);
    setSaveStatus('idle');
    
    sendMessage({
      type: 'pid',
      action: 'save',
      pid: pidValues,
      timestamp: Date.now()
    });
  };
  
  const getPIDConfig = () => {
    if (!isConnected) return;
    
    sendMessage({
      type: 'pid',
      action: 'get_config',
      timestamp: Date.now()
    });
  };
  
  const resetToDefaults = () => {
    setPidValues({
      kp: 1.0,
      ki: 0.1,
      kd: 0.01
    });
  };
  
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${
            status === 'connected' ? 'bg-green-500' : 
            status === 'connecting' ? 'bg-yellow-500' : 
            status === 'error' ? 'bg-red-500' : 'bg-gray-400'
          }`}></div>
          <span className="font-medium">PID Configuration</span>
          <span className="text-sm text-gray-500">({status})</span>
        </div>
        
        {!isConnected ? (
          <button 
            onClick={connect}
            disabled={status === 'connecting'}
            className="px-3 py-1 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed flex items-center gap-1"
          >
            {status === 'connecting' ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                <span>Connecting...</span>
              </>
            ) : (
              <>
                <Power size={14} />
                <span>Connect</span>
              </>
            )}
          </button>
        ) : (
          <button 
            onClick={disconnect}
            className="px-3 py-1 bg-red-600 text-white rounded-md text-sm hover:bg-red-700 flex items-center gap-1"
          >
            <Power size={14} />
            <span>Disconnect</span>
          </button>
        )}
      </div>
      
      <div className="space-y-4">
        <div>
          <label className="flex justify-between">
            <span className="text-sm font-medium text-gray-700">Kp (Proportional)</span>
            <span className="text-sm text-gray-500">{pidValues.kp.toFixed(2)}</span>
          </label>
          <input
            type="range"
            name="kp"
            min="0"
            max="10"
            step="0.1"
            value={pidValues.kp}
            onChange={handleChange}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
        </div>
        
        <div>
          <label className="flex justify-between">
            <span className="text-sm font-medium text-gray-700">Ki (Integral)</span>
            <span className="text-sm text-gray-500">{pidValues.ki.toFixed(2)}</span>
          </label>
          <input
            type="range"
            name="ki"
            min="0"
            max="5"
            step="0.01"
            value={pidValues.ki}
            onChange={handleChange}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
        </div>
        
        <div>
          <label className="flex justify-between">
            <span className="text-sm font-medium text-gray-700">Kd (Derivative)</span>
            <span className="text-sm text-gray-500">{pidValues.kd.toFixed(3)}</span>
          </label>
          <input
            type="range"
            name="kd"
            min="0"
            max="1"
            step="0.001"
            value={pidValues.kd}
            onChange={handleChange}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
          />
        </div>
      </div>
      
      <div className="flex gap-2 mt-2">
        <button
          onClick={handleSave}
          disabled={!isConnected || isSaving}
          className="flex-1 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-md flex items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? (
            <>
              <RefreshCw size={14} className="animate-spin" />
              <span>Saving...</span>
            </>
          ) : (
            <>
              <Save size={14} />
              <span>Save Configuration</span>
            </>
          )}
        </button>
        
        <button
          onClick={resetToDefaults}
          className="px-3 py-1.5 bg-gray-200 hover:bg-gray-300 rounded-md flex items-center justify-center"
        >
          <RotateCcw size={14} />
        </button>
      </div>
      
      {saveStatus === 'success' && (
        <div className="bg-green-100 border border-green-400 text-green-700 px-3 py-2 rounded text-sm flex items-center gap-1">
          PID configuration saved successfully!
        </div>
      )}
      
      {saveStatus === 'error' && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-3 py-2 rounded text-sm flex items-center gap-1">
          Failed to save PID configuration. Please try again.
        </div>
      )}
      
      <div className="border-t pt-3">
        <button
          onClick={getPIDConfig}
          disabled={!isConnected}
          className="w-full py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-md flex items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw size={14} />
          <span>Get Current Configuration</span>
        </button>
      </div>
    </div>
  );
};

export default PIDControlWidget;