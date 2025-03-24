import React, { useState, useEffect, ChangeEvent } from 'react';
import robotControlService, { RobotMessage, CommandResponse } from '../services/robotControlService';

interface RobotControlPanelProps {
  robotId: string;
}

const RobotControlPanel: React.FC<RobotControlPanelProps> = ({ robotId }) => {
  const [connected, setConnected] = useState<boolean>(false);
  const [speeds, setSpeeds] = useState<number[]>([0, 0, 0]);
  const [status, setStatus] = useState<string>('');
  const [lastResponse, setLastResponse] = useState<CommandResponse | null>(null);

  useEffect(() => {
    // Connect to the robot control service
    robotControlService.connect()
      .then(() => {
        setConnected(true);
        setStatus('Connected to robot control');
      })
      .catch((error: Error) => {
        setStatus(`Error connecting: ${error.message}`);
      });
    
    // Register for response messages
    const handleResponse = (message: RobotMessage) => {
      if (message.type.includes('response') || message.type === 'error') {
        const responseMsg = message as CommandResponse;
        setLastResponse(responseMsg);
        setStatus(`${responseMsg.type}: ${responseMsg.message}`);
      }
    };
    
    robotControlService.onMessage('*', handleResponse);
    
    // Clean up on unmount
    return () => {
      robotControlService.offMessage('*', handleResponse);
    };
  }, []);

  const handleSpeedChange = (index: number, value: string): void => {
    const newSpeeds = [...speeds];
    newSpeeds[index] = parseFloat(value);
    setSpeeds(newSpeeds);
  };

  const sendMotorCommand = async (): Promise<void> => {
    try {
      setStatus('Sending motor command...');
      const response = await robotControlService.setMotorSpeeds(robotId, speeds);
      setStatus(`Command sent: ${response.message}`);
    } catch (error) {
      setStatus(`Error: ${(error as Error).message}`);
    }
  };

  const sendEmergencyStop = async (): Promise<void> => {
    try {
      setStatus('Sending emergency stop...');
      const response = await robotControlService.emergencyStop(robotId);
      setStatus(`Emergency stop executed: ${response.message}`);
      setSpeeds([0, 0, 0]);
    } catch (error) {
      setStatus(`Error: ${(error as Error).message}`);
    }
  };

  return (
    <div className="robot-control-panel">
      <h2>Robot Control Panel</h2>
      <div className="connection-status">
        Status: {connected ? 'Connected' : 'Disconnected'}
      </div>
      
      <div className="motor-controls">
        <h3>Motor Speeds</h3>
        {[0, 1, 2].map((index) => (
          <div key={index} className="motor-control">
            <label htmlFor={`motor-${index}`}>Motor {index + 1}: </label>
            <input
              id={`motor-${index}`}
              type="range"
              min="-100"
              max="100"
              value={speeds[index]}
              onChange={(e: ChangeEvent<HTMLInputElement>) => 
                handleSpeedChange(index, e.target.value)
              }
            />
            <span>{speeds[index]}</span>
          </div>
        ))}
        
        <button 
          onClick={sendMotorCommand} 
          disabled={!connected}
          className="control-button"
        >
          Set Motor Speeds
        </button>
        
        <button 
          onClick={sendEmergencyStop} 
          disabled={!connected} 
          className="emergency-stop-button"
        >
          EMERGENCY STOP
        </button>
      </div>
      
      <div className="status-message">
        {status}
      </div>
      
      {lastResponse && (
        <div className="last-response">
          <h4>Last Response:</h4>
          <pre>{JSON.stringify(lastResponse, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export default RobotControlPanel;