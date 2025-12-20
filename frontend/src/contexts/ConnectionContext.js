import React, { createContext, useContext, useState } from 'react';

const ConnectionContext = createContext({
  connected: false,
  setConnected: () => {},
  credentials: null,
  setCredentials: () => {},
  testConnection: () => {},
});

export const ConnectionProvider = ({ children }) => {
  const [connected, setConnected] = useState(false);
  const [credentials, setCredentials] = useState(null);
  const [testConnectionFn, setTestConnectionFn] = useState(null);

  return (
    <ConnectionContext.Provider value={{ 
      connected, 
      setConnected,
      credentials,
      setCredentials,
      testConnection: testConnectionFn,
      setTestConnection: setTestConnectionFn
    }}>
      {children}
    </ConnectionContext.Provider>
  );
};

export const useConnection = () => {
  const context = useContext(ConnectionContext);
  if (!context) {
    throw new Error('useConnection must be used within ConnectionProvider');
  }
  return context;
};



