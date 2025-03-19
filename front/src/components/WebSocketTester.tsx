import React, { useState, useRef, useEffect } from 'react';
import { useWebSocket, WebSocketEndpoint } from '../services/WebSocketManager';

const WebSocketTester: React.FC = () => {
  const [activeEndpoint, setActiveEndpoint] = useState<WebSocketEndpoint>('/ws/robot1');
  const [message, setMessage] = useState('');
  const [responses, setResponses] = useState<string[]>([]);
  const [jsonMode, setJsonMode] = useState(true);
  const responseEndRef = useRef<HTMLDivElement>(null);
  
  const { 
    status, 
    isConnected, 
    connect, 
    disconnect, 
    sendMessage 
  } = useWebSocket(activeEndpoint, {
    autoConnect: false,
    onMessage: (data) => {
      const dataStr = typeof data === 'object' 
        ? JSON.stringify(data, null, 2) 
        : String(data);
        
      setResponses(prev => [...prev, `[${new Date().toLocaleTimeString()}] RECEIVED:\n${dataStr}`]);
    }
  });
  
  // Scroll to bottom when new responses arrive
  useEffect(() => {
    if (responseEndRef.current) {
      responseEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [responses]);
  
  const handleSend = () => {
    if (!isConnected || !message.trim()) return;
    
    try {
      const payload = jsonMode ? JSON.parse(message) : message;
      sendMessage(payload);
      
      // Log what was sent
      setResponses(prev => [
        ...prev, 
        `[${new Date().toLocaleTimeString()}] SENT:\n${
          typeof payload === 'object' ? JSON.stringify(payload, null, 2) : payload
        }`
      ]);
      
      // Optional: Clear input after sending
      setMessage('');
    } catch (e) {
      // Handle JSON parse error
      setResponses(prev => [
        ...prev, 
        `[${new Date().toLocaleTimeString()}] ERROR: Invalid JSON format`
      ]);
    }
  };
  
  const clearResponses = () => {
    setResponses([]);
  };
  
  const endpoints: WebSocketEndpoint[] = [
    '/ws/robot1', '/ws/robot2', '/ws/robot3', '/ws/robot4', '/ws/server'
  ];
  
  return (
    <div className="flex flex-col h-full">
      <h2 className="text-lg font-bold mb-4">WebSocket Tester</h2>
      
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Endpoint</label>
            <select 
              value={activeEndpoint}
              onChange={(e) => setActiveEndpoint(e.target.value as WebSocketEndpoint)}
              className="border rounded-md px-3 py-2"
              disabled={isConnected}
            >
              {endpoints.map(endpoint => (
                <option key={endpoint} value={endpoint}>{endpoint}</option>
              ))}
            </select>
          </div>
          
          <div>
            <div className="block text-sm font-medium text-gray-700 mb-1">Status</div>
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${
                status === 'connected' ? 'bg-green-500' : 
                status === 'connecting' ? 'bg-yellow-500' :
                status === 'error' ? 'bg-red-500' : 'bg-gray-400'
              }`}></div>
              <span className="text-sm">{status}</span>
            </div>
          </div>
        </div>
        
        <div>
          {!isConnected ? (
            <button 
              onClick={connect}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Connect
            </button>
          ) : (
            <button 
              onClick={disconnect}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
            >
              Disconnect
            </button>
          )}
        </div>
      </div>
      
      <div className="flex flex-col gap-2">
        <label className="block text-sm font-medium text-gray-700">Message</label>
        <div className="flex gap-4 mb-2">
          <div className="flex items-center">
            <input 
              type="radio" 
              id="json-mode" 
              checked={jsonMode} 
              onChange={() => setJsonMode(true)} 
              className="mr-2"
            />
            <label htmlFor="json-mode">JSON</label>
          </div>
          <div className="flex items-center">
            <input 
              type="radio" 
              id="text-mode" 
              checked={!jsonMode} 
              onChange={() => setJsonMode(false)} 
              className="mr-2"
            />
            <label htmlFor="text-mode">Text</label>
          </div>
        </div>
        
        <textarea 
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="border rounded-md p-3 h-40 font-mono"
          placeholder={jsonMode ? '{\n  "type": "get_status"\n}' : "Enter message..."}
        />
        
        <div className="flex justify-end gap-2">
          <button
            onClick={handleSend}
            disabled={!isConnected}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      </div>
      
      <div className="mt-4">
        <div className="flex justify-between items-center mb-2">
          <label className="block text-sm font-medium text-gray-700">Responses</label>
          <button
            onClick={clearResponses}
            className="px-2 py-1 bg-gray-200 text-gray-700 rounded-md text-xs hover:bg-gray-300"
          >
            Clear
          </button>
        </div>
        
        <div className="border rounded-md p-3 h-64 bg-gray-50 overflow-auto font-mono text-sm">
          {responses.map((response, index) => (
            <pre key={index} className={`whitespace-pre-wrap mb-2 pb-2 ${
              index < responses.length - 1 ? 'border-b border-gray-200' : ''
            } ${response.includes('SENT') ? 'text-blue-600' : 'text-green-600'}`}>
              {response}
            </pre>
          ))}
          <div ref={responseEndRef} />
        </div>
      </div>
    </div>
  );
};

export default WebSocketTester;