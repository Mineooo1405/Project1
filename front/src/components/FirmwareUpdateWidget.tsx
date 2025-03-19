import React, { useState, useRef } from "react";
import { Upload, AlertCircle, Check, RefreshCw } from "lucide-react";
import { useWebSocket, WebSocketEndpoint } from '../services/WebSocketManager';

// Thêm khai báo type để mở rộng WebSocketEndpoint
//type ExtendedEndpoint = WebSocketEndpoint | '/ws/firmware';

const FirmwareUpdateWidget: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  const [showErrorMessage, setShowErrorMessage] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Cập nhật cách gọi hook useWebSocket theo định dạng mới
  const {
    status,
    isConnected,
    connect,
    disconnect,
    sendMessage
  } = useWebSocket('/ws/server', {
    autoConnect: false,
    onMessage: (data) => {
      if (data.type === "status") {
        // Không làm gì
      } else if (data.type === "progress") {
        setProgress(data.value);
      } else if (data.type === "client_connected") {
        // Không làm gì
      } else if (data.type === "upload_complete") {
        setIsUploading(false);
        setShowSuccessMessage(true);
        setTimeout(() => setShowSuccessMessage(false), 3000);
      } else if (data.type === "error") {
        setErrorMessage(data.message || "Unknown error");
        setShowErrorMessage(true);
        setIsUploading(false);
        setTimeout(() => setShowErrorMessage(false), 5000);
      }
    },
    onConnect: () => {
      // Thông báo server rằng chúng ta muốn kết nối cho firmware updates
      sendMessage({ action: "start_firmware_server" });
    },
    onError: () => {
      setErrorMessage("Connection error");
      setShowErrorMessage(true);
      setTimeout(() => setShowErrorMessage(false), 5000);
    }
  });

  const startFirmwareServer = () => {
    connect();
  };

  const sendFirmware = async () => {
    if (!selectedFile || !isConnected) {
      setErrorMessage("No file selected or not connected");
      setShowErrorMessage(true);
      setTimeout(() => setShowErrorMessage(false), 5000);
      return;
    }
    
    try {
      setIsUploading(true);
      setProgress(0);
      
      sendMessage({
        action: "upload_firmware",
        filename: selectedFile.name,
        filesize: selectedFile.size
      });
      
      const reader = new FileReader();
      reader.readAsArrayBuffer(selectedFile);
      
      reader.onload = () => {
        const arrayBuffer = reader.result as ArrayBuffer;
        const bytes = new Uint8Array(arrayBuffer);
        
        const chunkSize = 1024 * 64; // 64KB chunks
        const totalChunks = Math.ceil(bytes.length / chunkSize);
        
        for (let i = 0; i < totalChunks; i++) {
          const start = i * chunkSize;
          const end = Math.min(bytes.length, start + chunkSize);
          const chunk = bytes.slice(start, end);
          
          const base64Chunk = btoa(
            Array.from(chunk)
              .map(byte => String.fromCharCode(byte))
              .join('')
          );
          
          sendMessage({
            action: "upload_chunk",
            chunk_index: i,
            total_chunks: totalChunks,
            data: base64Chunk
          });
          
          // Update progress locally since we're not waiting for server responses
          const currentProgress = Math.round((i + 1) / totalChunks * 100);
          if (currentProgress > progress) {
            setProgress(currentProgress);
          }
        }
        
        sendMessage({
          action: "upload_complete"
        });
      };
      
    } catch (error) {
      console.error("Failed to send firmware:", error);
      setIsUploading(false);
      setErrorMessage("Failed to send firmware");
      setShowErrorMessage(true);
      setTimeout(() => setShowErrorMessage(false), 5000);
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    
    if (file) {
      setProgress(0);
      setShowErrorMessage(false);
      setShowSuccessMessage(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}></div>
          <span className="text-sm font-medium">{status}</span>
        </div>
      </div>
      
      <div className="flex flex-wrap gap-2">
        <button
          onClick={startFirmwareServer}
          disabled={isConnected}
          className="flex items-center gap-2 bg-blue-600 text-white px-3 py-2 rounded-md text-sm hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed"
        >
          <RefreshCw size={16} className={status === 'connecting' ? 'animate-spin' : ''} />
          {isConnected ? "Connected" : status === 'connecting' ? "Connecting..." : "Start Firmware Server"}
        </button>
        
        {isConnected && (
          <>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-2 bg-gray-600 text-white px-3 py-2 rounded-md text-sm hover:bg-gray-700"
            >
              <Upload size={16} />
              Choose Firmware
            </button>
            
            <button
              onClick={sendFirmware}
              disabled={!selectedFile || isUploading}
              className="flex items-center gap-2 bg-green-600 text-white px-3 py-2 rounded-md text-sm hover:bg-green-700 disabled:bg-green-400 disabled:cursor-not-allowed"
            >
              {isUploading ? <RefreshCw size={16} className="animate-spin" /> : <Upload size={16} />}
              Send Firmware
            </button>
          </>
        )}
        
        {isConnected && (
          <button
            onClick={disconnect}
            className="flex items-center gap-2 bg-red-600 text-white px-3 py-2 rounded-md text-sm hover:bg-red-700"
          >
            Disconnect
          </button>
        )}
      </div>
      
      <input 
        type="file" 
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".bin"
        style={{ display: 'none' }}
      />
      
      {selectedFile && (
        <div className="flex items-center gap-2 bg-gray-100 p-2 rounded-md text-sm">
          <span>Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)</span>
        </div>
      )}
      
      {isUploading && (
        <div className="w-full">
          <div className="flex justify-between text-xs mb-1">
            <span>Uploading firmware...</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div 
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        </div>
      )}
      
      {showSuccessMessage && (
        <div className="flex items-center gap-2 bg-green-100 text-green-800 p-2 rounded-md text-sm">
          <Check size={16} />
          <span>Firmware uploaded successfully!</span>
        </div>
      )}
      
      {showErrorMessage && (
        <div className="flex items-center gap-2 bg-red-100 text-red-800 p-2 rounded-md text-sm">
          <AlertCircle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
};

export default FirmwareUpdateWidget;