import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useClient } from '../contexts/ClientContext';
import { useConnection } from '../contexts/ConnectionContext';
import { useActivityLog } from '../contexts/ActivityLogContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableFooter } from './ui/table';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Search, RefreshCw, Loader2 } from 'lucide-react';

const DataView = () => {
  const { selectedClientId } = useClient();
  const { setConnected, setCredentials, setTestConnection } = useConnection();
  const { addTerminalLine } = useActivityLog();
  const [activeTab, setActiveTab] = useState('customers');
  
  // Customers state
  const [customers, setCustomers] = useState([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [customersSearch, setCustomersSearch] = useState('');
  const [customersLastUpdated, setCustomersLastUpdated] = useState(null);
  
  // Products state
  const [products, setProducts] = useState([]);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsSearch, setProductsSearch] = useState('');
  const [productsLastUpdated, setProductsLastUpdated] = useState(null);
  
  const prevClientIdRef = useRef(selectedClientId);
  const prevTabRef = useRef(activeTab);
  const [refreshingCache, setRefreshingCache] = useState(false);

  // Initialize connection status
  useEffect(() => {
    if (!selectedClientId) {
      setConnected(false);
      setCredentials(null);
      return;
    }

    const checkConnection = async () => {
      try {
        const response = await axios.get(`/credentials/clients/${selectedClientId}`);
        const creds = response.data;
        
        if (creds && creds.account_id && creds.application_key) {
          setCredentials(creds);
          // Test connection
          try {
            await axios.post(`/credentials/clients/${selectedClientId}/test`);
            setConnected(true);
            addTerminalLine('success', 'Connected to Cin7 API');
          } catch (error) {
            setConnected(false);
            addTerminalLine('error', `Connection test failed: ${error.message}`);
          }
        } else {
          setConnected(false);
          setCredentials(null);
        }
      } catch (error) {
        setConnected(false);
        setCredentials(null);
        addTerminalLine('error', `Failed to load credentials: ${error.message}`);
      }
    };

    checkConnection();
  }, [selectedClientId, setConnected, setCredentials, addTerminalLine]);

  // Expose testConnection function
  useEffect(() => {
    const testConnection = async () => {
      if (!selectedClientId) {
        toast.error('Please select a client first');
        return;
      }

      try {
        addTerminalLine('info', 'Testing connection to Cin7...');
        await axios.post(`/credentials/clients/${selectedClientId}/test`);
        setConnected(true);
        addTerminalLine('success', 'Connected to Cin7 API');
        toast.success('Connected to Cin7');
      } catch (error) {
        setConnected(false);
        addTerminalLine('error', `Connection test failed: ${error.message}`);
        toast.error('Connection test failed');
      }
    };

    setTestConnection(() => testConnection);
  }, [selectedClientId, setConnected, setTestConnection, addTerminalLine]);

  // Load customers
  const loadCustomers = useCallback(async (searchQuery = '') => {
    if (!selectedClientId) {
      return;
    }

    try {
      setCustomersLoading(true);
      const params = { client_id: selectedClientId };
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      const response = await axios.get('/sales/cached-customers', { params });
      setCustomers(response.data.customers || []);
      setCustomersLastUpdated(response.data.last_updated || null);
    } catch (error) {
      console.error('Failed to load customers:', error);
      if (error.response?.status === 401) {
        toast.error('Please log in to view data');
      } else {
        toast.error(`Failed to load customers: ${error.response?.data?.error || error.message}`);
      }
    } finally {
      setCustomersLoading(false);
    }
  }, [selectedClientId]);

  // Load products
  const loadProducts = useCallback(async (searchQuery = '') => {
    if (!selectedClientId) {
      return;
    }

    try {
      setProductsLoading(true);
      const params = { client_id: selectedClientId };
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      const response = await axios.get('/sales/cached-products', { params });
      setProducts(response.data.products || []);
      setProductsLastUpdated(response.data.last_updated || null);
    } catch (error) {
      console.error('Failed to load products:', error);
      if (error.response?.status === 401) {
        toast.error('Please log in to view data');
      } else {
        toast.error(`Failed to load products: ${error.response?.data?.error || error.message}`);
      }
    } finally {
      setProductsLoading(false);
    }
  }, [selectedClientId]);

  // Refresh cache from Cin7 API
  const refreshCache = useCallback(async () => {
    if (!selectedClientId) {
      return;
    }

    try {
      setRefreshingCache(true);
      toast.info('Refreshing cache from Cin7...');
      
      const response = await axios.post('/sales/refresh-cache', {
        client_id: selectedClientId
      });
      
      toast.success(`Cache refreshed: ${response.data.customer_count || 0} customers, ${response.data.product_count || 0} products`);
      
      // Reload the current tab's data
      if (activeTab === 'customers') {
        await loadCustomers(customersSearch);
      } else {
        await loadProducts(productsSearch);
      }
    } catch (error) {
      console.error('Failed to refresh cache:', error);
      toast.error(`Failed to refresh cache: ${error.response?.data?.error || error.message}`);
    } finally {
      setRefreshingCache(false);
    }
  }, [selectedClientId, activeTab, customersSearch, productsSearch, loadCustomers, loadProducts]);

  // Load data when client, tab, or search changes (with debounce for search only)
  useEffect(() => {
    if (!selectedClientId) return;
    
    const clientChanged = prevClientIdRef.current !== selectedClientId;
    const tabChanged = prevTabRef.current !== activeTab;
    const isInitialLoad = clientChanged || tabChanged;
    
    prevClientIdRef.current = selectedClientId;
    prevTabRef.current = activeTab;
    
    // No debounce for initial load (client or tab change), debounce for search changes
    const delay = isInitialLoad ? 0 : 300;
    
    const timeoutId = setTimeout(() => {
      if (activeTab === 'customers') {
        loadCustomers(customersSearch);
      } else {
        loadProducts(productsSearch);
      }
    }, delay);

    return () => clearTimeout(timeoutId);
  }, [selectedClientId, activeTab, customersSearch, productsSearch, loadCustomers, loadProducts]);

  // Get customer table columns
  const getCustomerColumns = () => {
    if (customers.length === 0) return [];
    
    const allKeys = new Set();
    customers.forEach(customer => {
      Object.keys(customer).forEach(key => allKeys.add(key));
    });
    
    // Prioritize common fields
    const priorityKeys = ['Name', 'Email', 'Phone', 'ID', 'CompanyName', 'CustomerID'];
    const otherKeys = Array.from(allKeys).filter(key => !priorityKeys.includes(key));
    
    return [...priorityKeys.filter(key => allKeys.has(key)), ...otherKeys.sort()];
  };

  // Get product table columns
  const getProductColumns = () => {
    if (products.length === 0) return [];
    
    const allKeys = new Set();
    products.forEach(product => {
      Object.keys(product).forEach(key => allKeys.add(key));
    });
    
    // Prioritize common fields
    const priorityKeys = ['Name', 'SKU', 'Barcode', 'ID', 'ProductID'];
    const otherKeys = Array.from(allKeys).filter(key => !priorityKeys.includes(key));
    
    return [...priorityKeys.filter(key => allKeys.has(key)), ...otherKeys.sort()];
  };

  const customerColumns = getCustomerColumns();
  const productColumns = getProductColumns();

  const formatValue = (value) => {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  if (!selectedClientId) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground p-4">
        Please select a client to view data
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full min-h-0">
        <div className="p-6 pb-0 flex-shrink-0">
          <div className="space-y-3 mb-4">
            <div className="flex items-center gap-4">
              <TabsList className="h-9 p-1">
                <TabsTrigger value="customers" className="text-xs py-1.5 px-3">
                  Customers
                </TabsTrigger>
                <TabsTrigger value="products" className="text-xs py-1.5 px-3">
                  Products
                </TabsTrigger>
              </TabsList>
              {activeTab === 'customers' && (
                <div className="relative max-w-sm">
                  <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search customers..."
                    value={customersSearch}
                    onChange={(e) => setCustomersSearch(e.target.value)}
                    className="pl-8"
                  />
                </div>
              )}
              {activeTab === 'products' && (
                <div className="relative max-w-sm">
                  <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search products..."
                    value={productsSearch}
                    onChange={(e) => setProductsSearch(e.target.value)}
                    className="pl-8"
                  />
                </div>
              )}
              <div className="flex items-center gap-2 flex-1 justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={refreshCache}
                  disabled={refreshingCache || customersLoading || productsLoading}
                >
                  {refreshingCache ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
        <TabsContent value="customers" className="mt-0 flex-1 flex flex-col min-h-0 px-6 pb-6 data-[state=inactive]:hidden">
          <div className="flex-1 flex flex-col min-h-0">
            {customersLoading && customers.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Loading customers...</span>
              </div>
            ) : customers.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                No customers found. {customersSearch && 'Try adjusting your search.'}
              </div>
            ) : (
              <div className="flex-1 overflow-hidden border-[1px] rounded-md bg-white flex flex-col min-h-0">
                <div className="flex-1 overflow-auto">
                  <Table className="border-0">
                      <TableHeader className="sticky top-0 bg-white z-10">
                        <TableRow>
                          {customerColumns.map((column) => (
                            <TableHead key={column} className="text-xs font-semibold whitespace-nowrap">
                              {column}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {customers.map((customer, idx) => (
                          <TableRow key={idx}>
                            {customerColumns.map((column) => (
                              <TableCell key={column} className="text-xs whitespace-nowrap">
                                {formatValue(customer[column])}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  {(customers.length > 0 || customersLastUpdated) && (
                    <div className="sticky bottom-0 bg-gray-50 border-t px-4 py-1 z-10 flex items-center justify-between">
                      <div className="text-xs text-muted-foreground">
                        {customers.length} {customers.length === 1 ? 'customer' : 'customers'}
                      </div>
                      {customersLastUpdated && (
                        <div className="text-xs text-muted-foreground">
                          Last updated: {formatDate(customersLastUpdated)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
          </div>
        </TabsContent>

        <TabsContent value="products" className="mt-0 flex-1 flex flex-col min-h-0 px-6 pb-6 data-[state=inactive]:hidden">
          <div className="flex-1 flex flex-col min-h-0">
            {productsLoading && products.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Loading products...</span>
              </div>
            ) : products.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                No products found. {productsSearch && 'Try adjusting your search.'}
              </div>
            ) : (
              <div className="flex-1 overflow-hidden border-[1px] rounded-md bg-white flex flex-col min-h-0">
                <div className="flex-1 overflow-auto">
                  <Table className="border-0">
                      <TableHeader className="sticky top-0 bg-white z-10">
                        <TableRow>
                          {productColumns.map((column) => (
                            <TableHead key={column} className="text-xs font-semibold whitespace-nowrap">
                              {column}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {products.map((product, idx) => (
                          <TableRow key={idx}>
                            {productColumns.map((column) => (
                              <TableCell key={column} className="text-xs whitespace-nowrap">
                                {formatValue(product[column])}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  {(products.length > 0 || productsLastUpdated) && (
                    <div className="sticky bottom-0 bg-gray-50 border-t px-4 py-1 z-10 flex items-center justify-between">
                      <div className="text-xs text-muted-foreground">
                        {products.length} {products.length === 1 ? 'product' : 'products'}
                      </div>
                      {productsLastUpdated && (
                        <div className="text-xs text-muted-foreground">
                          Last updated: {formatDate(productsLastUpdated)}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default DataView;

