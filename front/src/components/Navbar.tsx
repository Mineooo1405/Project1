import React from 'react';
import { Home, Settings, Server } from 'lucide-react';
import { Link } from 'react-router-dom';
import TCPServerStatusButton from './TCPServerStatusButton';

const Navbar: React.FC = () => {
  return (
    <nav className="bg-white border-b border-gray-200 py-2 px-4 flex items-center justify-between">
      <div className="flex items-center space-x-4">
        <Link to="/" className="font-bold text-xl text-gray-800 flex items-center gap-2">
          <Server className="h-6 w-6 text-blue-600" />
          <span>Robot Dashboard</span>
        </Link>
        
        <div className="hidden md:flex space-x-4">
          <Link to="/" className="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium">
            Dashboard
          </Link>
          <Link to="/robots" className="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium">
            Robots
          </Link>
          <Link to="/analytics" className="text-gray-600 hover:text-gray-900 px-3 py-2 rounded-md text-sm font-medium">
            Analytics
          </Link>
        </div>
      </div>
      
      <div className="flex items-center gap-4">
        {/* TCP Server Status Button */}
        <TCPServerStatusButton />
        
        <Link to="/settings" className="text-gray-600 hover:text-gray-900">
          <Settings className="h-5 w-5" />
        </Link>
      </div>
    </nav>
  );
};

export default Navbar;