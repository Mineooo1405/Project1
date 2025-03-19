import React, { useState, useEffect } from 'react';
import { Server, AlertCircle } from 'lucide-react';

interface TCPServerStatusButtonProps {
  className?: string;
}

const TCPServerStatusButton: React.FC<TCPServerStatusButtonProps> = ({ className }) => {
  const [serverStatus, setServerStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkTCPServer = async () => {
    try {
      const response = await fetch('/api/check-tcp-server');
      const data = await response.json();
      
      setServerStatus(data.status === 'ok' ? 'connected' : 'disconnected');
      setLastChecked(new Date());
    } catch (err) {
      console.error('Error checking TCP server:', err);
      setServerStatus('disconnected');
      setLastChecked(new Date());
    }
  };

  useEffect(() => {
    checkTCPServer();
    
    // Check every 30 seconds
    const interval = setInterval(checkTCPServer, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className={`relative ${className}`}>
      <button 
        onClick={checkTCPServer}
        className={`bg-blue-600/50 hover:bg-blue-600 text-white px-3 py-1 rounded-md text-sm flex items-center gap-1 transition-colors
          ${serverStatus === 'connected' ? 'border-l-4 border-green-500' : 
            serverStatus === 'disconnected' ? 'border-l-4 border-red-500' : ''}`}
        title={`TCP Server is ${serverStatus}. Last checked: ${lastChecked?.toLocaleTimeString() || 'never'}`}
      >
        <Server size={16} className={serverStatus === 'checking' ? 'animate-pulse' : ''} />
        <span className="hidden sm:inline">
          TCP {serverStatus === 'connected' ? 'Online' : serverStatus === 'disconnected' ? 'Offline' : 'Checking...'}
        </span>
        {serverStatus === 'disconnected' && <AlertCircle size={14} className="text-red-300" />}
      </button>
    </div>
  );
};

export default TCPServerStatusButton;