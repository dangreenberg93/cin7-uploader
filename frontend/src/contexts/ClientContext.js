import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const ClientContext = createContext();

export const useClient = () => {
  const context = useContext(ClientContext);
  if (!context) {
    throw new Error('useClient must be used within a ClientProvider');
  }
  return context;
};

export const ClientProvider = ({ children }) => {
  const [selectedClientId, setSelectedClientId] = useState(() => {
    // Default client ID
    const defaultClientId = '97ff98b6-dd64-48f0-b139-31ee18798e10';
    return localStorage.getItem('selectedClientId') || defaultClientId;
  });
  const [selectedClient, setSelectedClient] = useState(null);
  const [clients, setClients] = useState([]); // Filtered: only active clients for profile selection
  const [allClients, setAllClients] = useState([]); // Unfiltered: all clients (for Admin page)
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadClients();
  }, []);

  useEffect(() => {
    if (selectedClientId) {
      localStorage.setItem('selectedClientId', selectedClientId);
      // Immediately set selectedClient from clients array if available
      const clientFromList = clients.find(c => c.id === selectedClientId);
      if (clientFromList) {
        setSelectedClient(clientFromList);
      }
      // Then load full details asynchronously
      loadClientDetails();
    } else {
      setSelectedClient(null);
    }
  }, [selectedClientId, clients]);

  const loadClients = async () => {
    try {
      const response = await axios.get('/clients');
      // Store all clients (unfiltered) for Admin page
      setAllClients(response.data);
      // Filter to only show active clients for profile selection
      const activeClients = response.data.filter(c => c.active !== false);
      setClients(activeClients);
      
      // If we have a saved client ID, validate it still exists and is active
      if (selectedClientId) {
        const clientExists = activeClients.find(c => c.id === selectedClientId);
        if (!clientExists) {
          // Current selection is inactive or doesn't exist, switch to first active client or default
          const defaultClientId = '97ff98b6-dd64-48f0-b139-31ee18798e10';
          const defaultExists = activeClients.find(c => c.id === defaultClientId);
          // Use default if available, otherwise use first active client
          const newClientId = defaultExists ? defaultClientId : (activeClients.length > 0 ? activeClients[0].id : '');
          if (newClientId) {
            setSelectedClientId(newClientId);
            // Set selectedClient immediately from the list
            const newClient = activeClients.find(c => c.id === newClientId);
            if (newClient) {
              setSelectedClient(newClient);
            }
          }
        } else {
          // Client exists, set it immediately from the list
          setSelectedClient(clientExists);
        }
      } else {
        // If no client selected, use default or first active client
        const defaultClientId = '97ff98b6-dd64-48f0-b139-31ee18798e10';
        const defaultExists = activeClients.find(c => c.id === defaultClientId);
        const clientIdToUse = defaultExists ? defaultClientId : (activeClients.length > 0 ? activeClients[0].id : '');
        if (clientIdToUse) {
          setSelectedClientId(clientIdToUse);
          // Set selectedClient immediately from the list
          const clientToUse = activeClients.find(c => c.id === clientIdToUse);
          if (clientToUse) {
            setSelectedClient(clientToUse);
          }
        }
      }
    } catch (error) {
      console.error('Failed to load clients:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadClientDetails = async () => {
    if (!selectedClientId) {
      setSelectedClient(null);
      return;
    }

    try {
      const response = await axios.get(`/clients/${selectedClientId}`);
      setSelectedClient(response.data);
    } catch (error) {
      console.error('Failed to load client details:', error);
      setSelectedClient(null);
    }
  };

  const value = {
    selectedClientId,
    setSelectedClientId,
    selectedClient,
    clients, // Active clients only (for profile selection)
    allClients, // All clients including inactive (for Admin page)
    loading,
    refreshClients: loadClients
  };

  return (
    <ClientContext.Provider value={value}>
      {children}
    </ClientContext.Provider>
  );
};



