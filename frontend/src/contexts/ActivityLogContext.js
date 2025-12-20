import React, { createContext, useContext, useState } from 'react';

const ActivityLogContext = createContext({
  showActivityLog: false,
  setShowActivityLog: () => {},
  terminalLines: [],
  setTerminalLines: () => {},
  addTerminalLine: () => {},
});

export const ActivityLogProvider = ({ children }) => {
  const [showActivityLog, setShowActivityLog] = useState(false);
  const [terminalLines, setTerminalLines] = useState([]);

  const addTerminalLine = (type, message) => {
    setTerminalLines(prev => {
      // Prevent duplicate consecutive messages
      const lastLine = prev[prev.length - 1];
      if (lastLine && lastLine.type === type && lastLine.message === message) {
        return prev;
      }
      return [...prev, { type, message, timestamp: new Date() }];
    });
  };

  return (
    <ActivityLogContext.Provider value={{ 
      showActivityLog, 
      setShowActivityLog,
      terminalLines,
      setTerminalLines,
      addTerminalLine
    }}>
      {children}
    </ActivityLogContext.Provider>
  );
};

export const useActivityLog = () => {
  const context = useContext(ActivityLogContext);
  if (!context) {
    throw new Error('useActivityLog must be used within ActivityLogProvider');
  }
  return context;
};



