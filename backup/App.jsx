import WebSocketManager from "./components/WebSocketManager";
import RobotSelector from "./components/RobotSelector";
import FeatureItem from "./components/FeatureItem";
import MainArea from "./components/MainArea";
import React, { useState } from "react";

const App = () => {
  const [robotStates, setRobotStates] = useState({});
  const [selectedRobotId, setSelectedRobotId] = useState(1);

  return (
    <div className="min-h-screen flex flex-col bg-gray-100">
      {/* Navbar */}
      <div className="bg-blue-700 text-white p-5 shadow-lg text-center text-2xl font-bold uppercase">
        🚀 Robot Dashboard
      </div>

      {/* Thanh chọn robot */}
      <RobotSelector
        selectedRobotId={selectedRobotId}
        setSelectedRobotId={setSelectedRobotId}
      />

      {/* Bố cục chính - responsive bằng cách flex-col trên mobile, md:flex-row cho màn to */}
      <div className="flex flex-1 flex-col md:flex-row">
        {/* Sidebar */}
        <div className="w-full md:w-72 bg-gray-900 text-white p-6 flex flex-col space-y-4 shadow-lg">
          <h2 className="text-lg font-semibold mb-2">📌 Chọn Widget</h2>
          <FeatureItem widgetType="📍 Map" />
          <FeatureItem widgetType="📊 Status" />
        </div>

        {/* Khu vực chính */}
        <div className="flex-1 p-6">
          <MainArea selectedRobotId={selectedRobotId} />
        </div>
      </div>

      {/* WebSocket */}
      <WebSocketManager setRobotStates={setRobotStates} />
    </div>
  );
};

export default App;
