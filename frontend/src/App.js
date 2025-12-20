import React, { useState, useEffect, useRef } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { Toaster } from 'sonner';
import Login from './components/Login';
import ResetPassword from './components/ResetPassword';
import SalesOrderUploader from './components/SalesOrderUploader';
import Admin from './components/Admin';
import CsvMappingConfig from './components/CsvMappingConfig';
import Cin7Settings from './components/Cin7Settings';
import { SidebarProvider, SidebarTrigger, SidebarInset } from './components/ui/sidebar';
import { AppSidebar } from './components/AppSidebar';
import { ClientProvider, useClient } from './contexts/ClientContext';
import { ActivityLogProvider, useActivityLog } from './contexts/ActivityLogContext';
import { ConnectionProvider, useConnection } from './contexts/ConnectionContext';
import { clearSupabaseClient } from './lib/supabase';
import { Button } from './components/ui/button';
import { Badge } from './components/ui/badge';
import { PanelRight, ChevronRight, ScrollText, CheckCircle2, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader } from './components/ui/card';
import { cn } from './lib/utils';

// Configure axios defaults
const apiUrl = process.env.REACT_APP_API_URL || (process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:5001/api');
axios.defaults.baseURL = apiUrl;

// Add token to requests if available
axios.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

function ActivityLogSidebar() {
  const { showActivityLog, setShowActivityLog, terminalLines } = useActivityLog();
  const location = useLocation();
  const terminalEndRef = React.useRef(null);

  React.useEffect(() => {
    if (showActivityLog && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [terminalLines, showActivityLog]);
  
  // Only show on home page
  if (location.pathname !== '/') {
    return null;
  }

  return (
    <aside
      className={cn(
        "flex h-full flex-col transition-all duration-300 ease-in-out overflow-hidden",
        showActivityLog ? "w-[30%] min-w-[300px] max-w-[500px]" : "w-0 min-w-0"
      )}
    >
      {showActivityLog && (
        <Card className="h-full flex flex-col bg-white m-2 rounded-md border border-gray-200 shadow-sm">
          <CardHeader className="h-10 pb-0 pt-0 px-4 flex-shrink-0 flex items-center border-b">
            <div className="flex items-center justify-between w-full h-full">
              <nav className="flex items-center gap-3">
                <span className="text-xs font-semibold text-foreground leading-none">Activity Log</span>
                <span className="text-xs text-muted-foreground hidden md:inline leading-none">Real-time updates and status</span>
              </nav>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs font-semibold"
                onClick={() => setShowActivityLog(false)}
              >
                <ChevronRight className="h-4 w-4 mr-2" />
                Hide logs
              </Button>
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-auto bg-gray-100 font-mono text-xs p-4 pt-5 rounded border-t border-gray-200">
            {terminalLines.map((line, idx) => (
              <div key={idx} className="mb-1">
                <span className="text-gray-500">
                  [{line.timestamp.toLocaleTimeString()}]
                </span>
                <span className={cn(
                  "ml-2",
                  line.type === 'success' && "text-green-600",
                  line.type === 'error' && "text-red-600",
                  line.type === 'warning' && "text-yellow-600",
                  line.type === 'info' && "text-blue-600"
                )}>
                  {line.message}
                </span>
              </div>
            ))}
            <div ref={terminalEndRef} />
          </CardContent>
        </Card>
      )}
    </aside>
  );
}

function AppHeaderContent() {
  const location = useLocation();
  const { showActivityLog, setShowActivityLog } = useActivityLog();
  const { connected, credentials, testConnection } = useConnection();
  const { selectedClient } = useClient();

  const getPageTitle = () => {
    if (location.pathname === '/admin') {
      return 'Admin';
    }
    if (location.pathname === '/mappings') {
      return 'CSV Mappings';
    }
    if (location.pathname === '/settings/cin7') {
      return 'Cin7 Config';
    }
    return 'Cin7 Uploader';
  };

  const getPageDescription = () => {
    if (location.pathname === '/admin') {
      return 'Manage clients and users';
    }
    if (location.pathname === '/mappings') {
      return 'Configure CSV column mappings';
    }
    if (location.pathname === '/settings/cin7') {
      return 'Configure order defaults';
    }
    return 'Upload CSV files and create sales orders in Cin7';
  };

  return (
    <header className="sticky top-0 z-10 flex h-10 shrink-0 items-center gap-3 border-b bg-white px-4 rounded-t-md border-gray-200">
      <SidebarTrigger />
      <nav className="flex items-center gap-3">
        <span className="text-xs font-semibold text-foreground">{getPageTitle()}</span>
        <span className="text-xs text-muted-foreground hidden md:inline">{getPageDescription()}</span>
      </nav>
      <div className="flex-1" />
      {location.pathname === '/' && selectedClient && (
        <>
          {connected ? (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500"></div>
              <span className="text-xs text-muted-foreground">Connected to Cin7</span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <XCircle className="w-3 h-3 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">Not Connected</span>
            </div>
          )}
          {!connected && credentials && testConnection && (
            <Button size="sm" onClick={testConnection}>
              Test Connection
            </Button>
          )}
        </>
      )}
      {location.pathname === '/' && !showActivityLog && (
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={() => setShowActivityLog(true)}
        >
          <ScrollText className="h-4 w-4" />
          <span className="sr-only">Show Activity Log</span>
        </Button>
      )}
    </header>
  );
}

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true; // Prevent state updates if component unmounts
    
    // Check for OAuth callback with token
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const email = urlParams.get('email');
    const error = urlParams.get('error');
    
    // Clean up URL immediately to prevent redirect loops
    if (token || error) {
      window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    if (error) {
      // Handle OAuth errors
      if (isMounted) {
        setLoading(false);
        setIsAuthenticated(false);
      }
      return;
    }
    
    const checkAuth = async () => {
      const tokenToUse = token || localStorage.getItem('token');
      
      if (tokenToUse) {
        // Store token if it came from URL
        if (token) {
          localStorage.setItem('token', token);
        }
        
        try {
          const response = await axios.get('/auth/me');
          if (isMounted) {
            setUser(response.data);
            setIsAuthenticated(true);
            setLoading(false);
          }
        } catch (error) {
          console.error('Auth error:', error.response?.status, error.response?.data);
          if (isMounted) {
            localStorage.removeItem('token');
            setIsAuthenticated(false);
            setLoading(false);
          }
        }
      } else {
        if (isMounted) {
          setLoading(false);
        }
      }
    };
    
    checkAuth();
    
    return () => {
      isMounted = false;
    };
  }, []);

  const handleLogin = (userData, token) => {
    localStorage.setItem('token', token);
    setUser(userData);
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    clearSupabaseClient();
    setUser(null);
    setIsAuthenticated(false);
  };

  // Check if user is admin
  const isAdmin = user && (user.role === 'admin' || user.email === 'dan@paleblue.nyc');

  // Redirect non-admins away from admin page
  useEffect(() => {
    if (isAuthenticated && !isAdmin && location.pathname === '/admin') {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, isAdmin, location.pathname, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  // Check if we're on the reset password page (should be accessible without auth)
  const isResetPasswordPage = location.pathname === '/reset-password';
  
  if (!isAuthenticated && !isResetPasswordPage) {
    return (
      <>
        <Toaster 
          position="bottom-right" 
          closeButton 
        />
        <Login onLogin={handleLogin} />
      </>
    );
  }

  // Show reset password page even if not authenticated
  if (isResetPasswordPage) {
    return (
      <>
        <Toaster 
          position="bottom-right" 
          closeButton 
        />
        <ResetPassword onLogin={handleLogin} />
      </>
    );
  }

  return (
    <>
      <Toaster 
        position="bottom-right" 
        closeButton 
      />
      <ClientProvider>
        <ConnectionProvider>
          <ActivityLogProvider>
          <div className="flex h-screen w-full overflow-hidden bg-gray-50">
            <SidebarProvider>
              <AppSidebar user={user} onLogout={handleLogout} />
              <div className="flex flex-1 min-w-0">
                <SidebarInset className="bg-white m-2 rounded-md border border-gray-200 min-w-0 shadow-sm flex-1">
                  <AppHeaderContent />
                  <main className="flex flex-1 flex-col overflow-hidden bg-white rounded-b-md min-h-0 min-w-0">
                    <Routes>
                      <Route path="/" element={<SalesOrderUploader user={user} />} />
                      <Route path="/mappings" element={<CsvMappingConfig />} />
                      <Route path="/settings/cin7" element={<Cin7Settings />} />
                      {isAdmin ? (
                        <Route path="/admin" element={<Admin user={user} />} />
                      ) : (
                        <Route path="/admin" element={<div className="p-4 text-center text-muted-foreground">Access denied. Admin access is restricted.</div>} />
                      )}
                    </Routes>
                  </main>
                </SidebarInset>
                <ActivityLogSidebar />
              </div>
            </SidebarProvider>
      </div>
      </ActivityLogProvider>
      </ConnectionProvider>
      </ClientProvider>
    </>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;



