import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
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
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Checkbox } from './ui/checkbox';
import { Search, RefreshCw, Loader2, Columns, Download, CheckCircle2, Circle, Check } from 'lucide-react';
import { Badge } from './ui/badge';

const DataView = () => {
  const location = useLocation();
  const { selectedClientId } = useClient();
  const { setConnected, setCredentials, setTestConnection } = useConnection();
  const { addTerminalLine } = useActivityLog();
  const [activeTab, setActiveTab] = useState('customers');
  
  // Customers state
  const [customers, setCustomers] = useState([]);
  const [customersLoading, setCustomersLoading] = useState(false);
  const [customersSearch, setCustomersSearch] = useState('');
  const [customersLastUpdated, setCustomersLastUpdated] = useState(null);
  const [customersFilter, setCustomersFilter] = useState('all'); // 'all' or 'new'
  const [newCustomersCount, setNewCustomersCount] = useState(0);
  
  // Products state
  const [products, setProducts] = useState([]);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsSearch, setProductsSearch] = useState('');
  const [productsLastUpdated, setProductsLastUpdated] = useState(null);
  const [productsFilter, setProductsFilter] = useState('all'); // 'all' or 'new'
  const [newProductsCount, setNewProductsCount] = useState(0);
  
  // Column visibility state
  const [visibleCustomerColumns, setVisibleCustomerColumns] = useState(new Set());
  const [visibleProductColumns, setVisibleProductColumns] = useState(new Set());
  const [columnSearch, setColumnSearch] = useState('');
  
  const prevClientIdRef = useRef(selectedClientId);
  const prevTabRef = useRef(activeTab);
  const prevCustomersFilterRef = useRef('all');
  const prevProductsFilterRef = useRef('all');
  const [refreshingCache, setRefreshingCache] = useState(false);
  const customersTabContentRef = useRef(null);
  

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

  // Load customers - always load all data, filter client-side
  const loadCustomers = useCallback(async (searchQuery = '') => {
    if (!selectedClientId) {
      return;
    }

    try {
      // Only show loading spinner on initial load (when no data exists)
      const isInitialLoad = customers.length === 0;
      if (isInitialLoad) {
        setCustomersLoading(true);
      }
      const params = { client_id: selectedClientId };
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      // Always load all customers - filtering happens client-side
      const response = await axios.get('/sales/cached-customers', { params });
      const customersData = response.data.customers || [];
      // Debug: log first customer keys to see order
      if (customersData.length > 0) {
        console.log('First customer keys order:', Object.keys(customersData[0]));
      }
      // Update data atomically - this prevents flashing
      setCustomers(customersData);
      setCustomersLastUpdated(response.data.last_updated || null);
      
      // Counts are loaded separately from API endpoints, so we don't need to calculate here
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
  }, [selectedClientId, customers.length]);

  // Load products - always load all data, filter client-side
  const loadProducts = useCallback(async (searchQuery = '') => {
    if (!selectedClientId) {
      return;
    }

    try {
      // Only show loading spinner on initial load (when no data exists)
      const isInitialLoad = products.length === 0;
      if (isInitialLoad) {
        setProductsLoading(true);
      }
      const params = { client_id: selectedClientId };
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      // Always load all products - filtering happens client-side
      // Add timestamp to prevent caching
      params._t = Date.now();
      const response = await axios.get('/sales/cached-products', { params });
      const productsData = response.data.products || [];
      // Debug: log first product keys to see order
      if (productsData.length > 0) {
        console.log('First product keys order:', Object.keys(productsData[0]));
      }
      console.log('Products loaded:', productsData.length || 0, 'products');
      // Update data atomically - this prevents flashing
      setProducts(productsData);
      setProductsLastUpdated(response.data.last_updated || null);
      
      // Counts are loaded separately from API endpoints, so we don't need to calculate here
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
  }, [selectedClientId, products.length]);

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
      
      const customerCount = response.data.customer_count || 0;
      const productCount = response.data.product_count || 0;
      console.log('Cache refresh response:', { customerCount, productCount });
      toast.success(`Cache refreshed: ${customerCount} customers, ${productCount} products`);
      
      // Small delay to ensure database commit is complete and visible
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Reload both customers and products since both are refreshed
      // Use allSettled so both loads happen even if one fails
      console.log('Reloading customers and products after cache refresh...');
      const results = await Promise.allSettled([
        loadCustomers(customersSearch, customersFilter),
        loadProducts(productsSearch, productsFilter)
      ]);
      
      // Log any failures for debugging
      results.forEach((result, index) => {
        if (result.status === 'rejected') {
          console.error(`Failed to reload ${index === 0 ? 'customers' : 'products'}:`, result.reason);
        } else {
          console.log(`Successfully reloaded ${index === 0 ? 'customers' : 'products'}`);
        }
      });
    } catch (error) {
      console.error('Failed to refresh cache:', error);
      toast.error(`Failed to refresh cache: ${error.response?.data?.error || error.message}`);
    } finally {
      setRefreshingCache(false);
    }
  }, [selectedClientId, activeTab, customersSearch, productsSearch, loadCustomers, loadProducts]);

  // Reset column search when switching tabs
  useEffect(() => {
    setColumnSearch('');
  }, [activeTab]);

  // Load data when client, tab, search, or filter changes (with debounce for search only)
  useEffect(() => {
    if (!selectedClientId) return;
    
    const clientChanged = prevClientIdRef.current !== selectedClientId;
    const tabChanged = prevTabRef.current !== activeTab;
    const customersFilterChanged = prevCustomersFilterRef.current !== customersFilter;
    const productsFilterChanged = prevProductsFilterRef.current !== productsFilter;
    
    prevClientIdRef.current = selectedClientId;
    prevTabRef.current = activeTab;
    prevCustomersFilterRef.current = customersFilter;
    prevProductsFilterRef.current = productsFilter;
    
    // No debounce for initial load or tab change - debounce only for search changes
    // Filter changes don't trigger API calls - filtering is client-side
    const isInitialLoad = clientChanged || tabChanged;
    const delay = isInitialLoad ? 0 : 300;
    
    // Only load data when client, tab, or search changes - NOT when filter changes
    // Filtering happens client-side, so no API call needed
    const timeoutId = setTimeout(() => {
      if (activeTab === 'customers') {
        loadCustomers(customersSearch);
      } else {
        loadProducts(productsSearch);
      }
    }, delay);

    return () => clearTimeout(timeoutId);
  }, [selectedClientId, activeTab, customersSearch, productsSearch, loadCustomers, loadProducts]);
  
  // Update filter and tab from URL params when location changes
  useEffect(() => {
    const urlParams = new URLSearchParams(location.search);
    const filter = urlParams.get('filter');
    const tab = urlParams.get('tab');
    
    // Set active tab from URL if provided
    if (tab === 'customers' || tab === 'products') {
      setActiveTab(tab);
    }
    
    // Set filter based on URL
    if (filter === 'new') {
      if (tab === 'customers') {
        setCustomersFilter('new');
      } else if (tab === 'products') {
        setProductsFilter('new');
      }
    } else if (filter === 'all' || !filter) {
      // Reset filters to 'all' if filter is 'all' or not specified
      if (tab === 'customers') {
        setCustomersFilter('all');
      } else if (tab === 'products') {
        setProductsFilter('all');
      }
    }
  }, [location.search]);

  // Load counts separately from API endpoints for accurate badge counts
  useEffect(() => {
    if (!selectedClientId) {
      setNewCustomersCount(0);
      setNewProductsCount(0);
      return;
    }

    const loadCounts = async () => {
      try {
        const [customersResponse, productsResponse] = await Promise.all([
          axios.get(`/sales/cached-customers/new-count?client_id=${selectedClientId}`).catch(() => ({ data: { count: 0 } })),
          axios.get(`/sales/cached-products/new-count?client_id=${selectedClientId}`).catch(() => ({ data: { count: 0 } }))
        ]);
        
        const customersCount = customersResponse.data.count || 0;
        const productsCount = productsResponse.data.count || 0;
        
        setNewCustomersCount(customersCount);
        setNewProductsCount(productsCount);
        
        // Switch to 'all' if 'new' filter is active but count is 0
        if (customersFilter === 'new' && customersCount === 0) {
          setCustomersFilter('all');
        }
        if (productsFilter === 'new' && productsCount === 0) {
          setProductsFilter('all');
        }
      } catch (error) {
        console.error('Failed to load counts:', error);
      }
    };

    loadCounts();
    
    // Refresh counts when data is refreshed or when marking as reviewed
    const handleRefreshCounts = () => {
      loadCounts();
    };
    
    window.addEventListener('refreshSidebarCounts', handleRefreshCounts);
    
    return () => {
      window.removeEventListener('refreshSidebarCounts', handleRefreshCounts);
    };
  }, [selectedClientId, customersFilter, productsFilter]);

  // Hardcoded API response column order (from Cin7 API)
  const API_CUSTOMER_COLUMN_ORDER = [
    'Name', 'DisplayName', 'Currency', 'PaymentTerm', 'Discount', 'TaxRule', 'Carrier',
    'SalesRepresentative', 'Location', 'Comments', 'AccountReceivable', 'RevenueAccount', 'PriceTier',
    'TaxNumber', 'AdditionalAttribute1', 'AdditionalAttribute2', 'AdditionalAttribute3', 'AdditionalAttribute4',
    'AdditionalAttribute5', 'AdditionalAttribute6', 'AdditionalAttribute7', 'AdditionalAttribute8',
    'AdditionalAttribute9', 'AdditionalAttribute10', 'AttributeSet', 'Tags', 'Status', 'CreditLimit',
    'IsOnCreditHold', 'LastModifiedOn', 'Addresses', 'Contacts', 'ProductPrices'
  ];

  const API_PRODUCT_COLUMN_ORDER = [
    'Name', 'SKU', 'Category', 'Brand', 'Type', 'CostingMethod', 'DropShipMode', 'DefaultLocation',
    'Length', 'Width', 'Height', 'Weight', 'UOM', 'WeightUnits', 'DimensionsUnits', 'Barcode',
    'MinimumBeforeReorder', 'ReorderQuantity', 'PriceTier1', 'PriceTier2', 'PriceTier3', 'PriceTier4',
    'PriceTier5', 'PriceTier6', 'PriceTier7', 'PriceTier8', 'PriceTier9', 'PriceTier10', 'PriceTiers',
    'AverageCost', 'ShortDescription', 'InternalNote', 'Description', 'AdditionalAttribute1',
    'AdditionalAttribute2', 'AdditionalAttribute3', 'AdditionalAttribute4', 'AdditionalAttribute5',
    'AdditionalAttribute6', 'AdditionalAttribute7', 'AdditionalAttribute8', 'AdditionalAttribute9',
    'AdditionalAttribute10', 'AttributeSet', 'DiscountRule', 'Tags', 'Status', 'StockLocator',
    'COGSAccount', 'RevenueAccount', 'ExpenseAccount', 'InventoryAccount', 'PurchaseTaxRule',
    'SaleTaxRule', 'LastModifiedOn', 'Sellable', 'PickZones', 'BillOfMaterial', 'AutoAssembly',
    'AutoDisassembly', 'QuantityToProduce', 'AlwaysShowQuantity', 'AssemblyInstructionURL',
    'AssemblyCostEstimationMethod', 'Suppliers', 'ReorderLevels', 'BillOfMaterialsProducts',
    'BillOfMaterialsServices', 'Movements', 'Attachments', 'BOMType', 'WarrantyName', 'CustomPrices',
    'CartonHeight', 'CartonWidth', 'CartonLength', 'CartonQuantity', 'CartonInnerQuantity', 'HSCode',
    'CountryOfOrigin', 'CountryOfOriginCode', 'CreatedDate'
  ];

  // Get customer table columns - use hardcoded API order
  const getCustomerColumns = () => {
    if (customers.length === 0) return [];
    
    // Get all unique keys from all customers
    const allKeysSet = new Set();
    customers.forEach(customer => {
      Object.keys(customer).forEach(key => allKeysSet.add(key));
    });
    
    // Start with Name first (for sticky column)
    const orderedColumns = ['Name'];
    
    // Add columns in API order that exist in the data
    for (const key of API_CUSTOMER_COLUMN_ORDER) {
      if (key !== 'Name' && allKeysSet.has(key)) {
        orderedColumns.push(key);
      }
    }
    
    // Add any additional keys that aren't in the standard order
    for (const key of Array.from(allKeysSet).sort()) {
      if (key !== 'ID' && key !== 'Name' && !API_CUSTOMER_COLUMN_ORDER.includes(key)) {
        orderedColumns.push(key);
      }
    }
    
    return orderedColumns;
  };

  // Get product table columns - use hardcoded API order
  const getProductColumns = () => {
    if (products.length === 0) return [];
    
    // Get all unique keys from all products
    const allKeysSet = new Set();
    products.forEach(product => {
      Object.keys(product).forEach(key => allKeysSet.add(key));
    });
    
    // Start with Name first (for sticky column)
    const orderedColumns = ['Name'];
    
    // Add columns in API order that exist in the data
    for (const key of API_PRODUCT_COLUMN_ORDER) {
      if (key !== 'Name' && allKeysSet.has(key)) {
        orderedColumns.push(key);
      }
    }
    
    // Add any additional keys that aren't in the standard order
    for (const key of Array.from(allKeysSet).sort()) {
      if (key !== 'ID' && key !== 'Name' && !API_PRODUCT_COLUMN_ORDER.includes(key)) {
        orderedColumns.push(key);
      }
    }
    
    return orderedColumns;
  };

  const allCustomerColumns = useMemo(() => getCustomerColumns(), [customers]);
  const allProductColumns = useMemo(() => getProductColumns(), [products]);

  // Track the last column set we initialized with (to detect when columns actually change)
  const lastCustomerColumnsRef = useRef('');
  const lastProductColumnsRef = useRef('');

  // Reset initialization refs when client changes
  useEffect(() => {
    lastCustomerColumnsRef.current = '';
    lastProductColumnsRef.current = '';
    setVisibleCustomerColumns(new Set());
    setVisibleProductColumns(new Set());
  }, [selectedClientId]);

  // Initialize visible columns when columns first become available or when they change
  useEffect(() => {
    const currentColumnsString = allCustomerColumns.join(',');
    if (allCustomerColumns.length > 0 && currentColumnsString !== lastCustomerColumnsRef.current) {
      // Only initialize if we haven't initialized yet (empty string means first time)
      if (lastCustomerColumnsRef.current === '') {
        setVisibleCustomerColumns(new Set(allCustomerColumns));
      }
      lastCustomerColumnsRef.current = currentColumnsString;
    }
  }, [allCustomerColumns]);

  useEffect(() => {
    const currentColumnsString = allProductColumns.join(',');
    if (allProductColumns.length > 0 && currentColumnsString !== lastProductColumnsRef.current) {
      // Only initialize if we haven't initialized yet (empty string means first time)
      if (lastProductColumnsRef.current === '') {
        setVisibleProductColumns(new Set(allProductColumns));
      }
      lastProductColumnsRef.current = currentColumnsString;
    }
  }, [allProductColumns]);

  // Ensure Name is always in the visible set (only check when columns change, not on every toggle)
  const customerColumnsString = useMemo(() => allCustomerColumns.join(','), [allCustomerColumns]);
  const productColumnsString = useMemo(() => allProductColumns.join(','), [allProductColumns]);

  useEffect(() => {
    if (allCustomerColumns.includes('Name') && !visibleCustomerColumns.has('Name')) {
      setVisibleCustomerColumns(prev => {
        const newSet = new Set(prev);
        newSet.add('Name');
        return newSet;
      });
    }
  }, [customerColumnsString]); // Only when columns actually change

  useEffect(() => {
    if (allProductColumns.includes('Name') && !visibleProductColumns.has('Name')) {
      setVisibleProductColumns(prev => {
        const newSet = new Set(prev);
        newSet.add('Name');
        return newSet;
      });
    }
  }, [productColumnsString]); // Only when columns actually change

  // Get filtered visible columns (always include Name, preserve API order)
  const getVisibleCustomerColumns = () => {
    // Filter allCustomerColumns (which preserves API order) to only include visible ones
    const visible = allCustomerColumns.filter(col => 
      visibleCustomerColumns.has(col) || col === 'Name'
    );
    return visible.length > 0 ? visible : allCustomerColumns;
  };

  const getVisibleProductColumns = () => {
    // Filter allProductColumns (which preserves API order) to only include visible ones
    const visible = allProductColumns.filter(col => 
      visibleProductColumns.has(col) || col === 'Name'
    );
    return visible.length > 0 ? visible : allProductColumns;
  };

  // Ensure Name is always first for sticky column, preserve API order for rest
  const customerColumns = useMemo(() => {
    const cols = getVisibleCustomerColumns();
    // Preserve order: Name first, then rest in original API order
    if (cols.includes('Name')) {
      const nameIndex = cols.indexOf('Name');
      return ['Name', ...cols.slice(0, nameIndex), ...cols.slice(nameIndex + 1)];
    }
    return cols;
  }, [visibleCustomerColumns, allCustomerColumns]);
  
  const productColumns = useMemo(() => {
    const cols = getVisibleProductColumns();
    // Preserve order: Name first, then rest in original API order
    if (cols.includes('Name')) {
      const nameIndex = cols.indexOf('Name');
      return ['Name', ...cols.slice(0, nameIndex), ...cols.slice(nameIndex + 1)];
    }
    return cols;
  }, [visibleProductColumns, allProductColumns]);

  // Toggle column visibility
  const toggleCustomerColumn = useCallback((column) => {
    if (column === 'Name') return; // Name cannot be toggled off
    setVisibleCustomerColumns(prev => {
      const newSet = new Set(prev);
      if (newSet.has(column)) {
        newSet.delete(column);
      } else {
        newSet.add(column);
      }
      return newSet;
    });
  }, []);

  const toggleProductColumn = useCallback((column) => {
    if (column === 'Name') return; // Name cannot be toggled off
    setVisibleProductColumns(prev => {
      const newSet = new Set(prev);
      if (newSet.has(column)) {
        newSet.delete(column);
      } else {
        newSet.add(column);
      }
      return newSet;
    });
  }, []);

  // Select all columns
  const selectAllCustomerColumns = () => {
    setVisibleCustomerColumns(new Set(allCustomerColumns));
  };

  const selectAllProductColumns = () => {
    setVisibleProductColumns(new Set(allProductColumns));
  };

  // Deselect all columns (but keep Name)
  const deselectAllCustomerColumns = () => {
    if (allCustomerColumns.includes('Name')) {
      setVisibleCustomerColumns(new Set(['Name']));
    } else {
      setVisibleCustomerColumns(new Set());
    }
  };

  const deselectAllProductColumns = () => {
    if (allProductColumns.includes('Name')) {
      setVisibleProductColumns(new Set(['Name']));
    } else {
      setVisibleProductColumns(new Set());
    }
  };

  // Check if all columns are selected
  const areAllCustomerColumnsSelected = () => {
    if (allCustomerColumns.length === 0) return false;
    return allCustomerColumns.every(col => visibleCustomerColumns.has(col));
  };

  const areAllProductColumnsSelected = () => {
    if (allProductColumns.length === 0) return false;
    return allProductColumns.every(col => visibleProductColumns.has(col));
  };

  // Check if only Name is visible (or nothing)
  const isOnlyNameVisibleForCustomers = () => {
    const visible = Array.from(visibleCustomerColumns);
    return visible.length === 0 || (visible.length === 1 && visible[0] === 'Name');
  };

  const isOnlyNameVisibleForProducts = () => {
    const visible = Array.from(visibleProductColumns);
    return visible.length === 0 || (visible.length === 1 && visible[0] === 'Name');
  };

  // Get filtered columns for popover (based on search)
  const getFilteredCustomerColumns = () => {
    if (!columnSearch.trim()) return allCustomerColumns;
    const searchLower = columnSearch.toLowerCase();
    return allCustomerColumns.filter(col => 
      col.toLowerCase().includes(searchLower)
    );
  };

  const getFilteredProductColumns = () => {
    if (!columnSearch.trim()) return allProductColumns;
    const searchLower = columnSearch.toLowerCase();
    return allProductColumns.filter(col => 
      col.toLowerCase().includes(searchLower)
    );
  };

  // Download CSV function
  const downloadCSV = useCallback(() => {
    const isCustomers = activeTab === 'customers';
    const data = isCustomers ? customers : products;
    const visibleCols = isCustomers ? customerColumns : productColumns;
    
    if (data.length === 0) {
      toast.error('No data to download');
      return;
    }

    // Check if ID exists in the data
    const hasID = data.length > 0 && 'ID' in data[0];
    
    // Ensure ID is first, then other visible columns (excluding ID if it's already in visibleCols)
    const columnsToExport = hasID 
      ? ['ID', ...visibleCols.filter(col => col !== 'ID')]
      : visibleCols;
    
    // Create CSV header
    const headers = columnsToExport.map(col => `"${col}"`).join(',');
    
    // Create CSV rows
    const rows = data.map(item => {
      return columnsToExport.map(col => {
        let value = item[col];
        if (value === null || value === undefined) {
          value = '';
        } else if (typeof value === 'object') {
          value = JSON.stringify(value);
        } else {
          value = String(value);
        }
        // Escape quotes and wrap in quotes
        value = value.replace(/"/g, '""');
        return `"${value}"`;
      }).join(',');
    });
    
    // Combine header and rows
    const csvContent = [headers, ...rows].join('\n');
    
    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    const dateStr = new Date().toISOString().split('T')[0];
    link.setAttribute('download', `${isCustomers ? 'customers' : 'products'}_${dateStr}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    
    toast.success(`Downloaded ${isCustomers ? 'customers' : 'products'} CSV`);
  }, [activeTab, customers, products, customerColumns, productColumns]);

  // Mark customer/product as reviewed
  const markAsReviewed = useCallback(async (cacheId, type) => {
    try {
      const endpoint = type === 'customer' 
        ? `/sales/cached-customers/${cacheId}/review`
        : `/sales/cached-products/${cacheId}/review`;
      
      await axios.post(endpoint);
      toast.success(`${type === 'customer' ? 'Customer' : 'Product'} marked as reviewed`);
      
      // Reload data
      if (type === 'customer') {
        loadCustomers(customersSearch, customersFilter);
      } else {
        loadProducts(productsSearch, productsFilter);
      }
      
      // Trigger sidebar refresh
      window.dispatchEvent(new Event('refreshSidebarCounts'));
    } catch (error) {
      console.error(`Failed to mark ${type} as reviewed:`, error);
      toast.error(`Failed to mark as reviewed: ${error.response?.data?.error || error.message}`);
    }
  }, [customersSearch, customersFilter, productsSearch, productsFilter, loadCustomers, loadProducts]);

  const formatValue = (value) => {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    try {
      // Backend sends UTC times in ISO format without 'Z' suffix
      // We need to append 'Z' to tell JavaScript it's UTC, then it will convert to local time
      let dateStr = dateString;
      // If the string doesn't end with 'Z' and doesn't have a timezone offset (+/-), assume it's UTC
      if (!dateStr.endsWith('Z') && !dateStr.match(/[+-]\d{2}:\d{2}$/)) {
        dateStr = dateStr + 'Z';
      }
      const date = new Date(dateStr);
      // Check if date is valid
      if (isNaN(date.getTime())) return '-';
      // Format as local date and time - toLocaleString automatically converts UTC to local timezone
      return date.toLocaleString('en-US', {
        month: '2-digit',
        day: '2-digit',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });
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
                <>
                  <div className="relative max-w-sm">
                    <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input
                      placeholder="Search customers..."
                      value={customersSearch}
                      onChange={(e) => setCustomersSearch(e.target.value)}
                      className="pl-7 h-9 text-xs"
                    />
                  </div>
                  <Tabs value={customersFilter} onValueChange={setCustomersFilter} className="w-auto">
                    <TabsList className="h-9 p-1">
                      <TabsTrigger value="all" className="text-xs py-1.5 px-3">
                        All
                      </TabsTrigger>
                      <TabsTrigger 
                        value="new" 
                        className="text-xs py-1.5 px-3"
                        disabled={newCustomersCount === 0}
                      >
                        New {newCustomersCount > 0 && (
                          <Badge variant="default" className="ml-1.5 text-[10px] px-1 py-0 h-4 bg-blue-500">
                            {newCustomersCount}
                          </Badge>
                        )}
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </>
              )}
              {activeTab === 'products' && (
                <>
                  <div className="relative max-w-sm">
                    <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input
                      placeholder="Search products..."
                      value={productsSearch}
                      onChange={(e) => setProductsSearch(e.target.value)}
                      className="pl-7 h-9 text-xs"
                    />
                  </div>
                  <Tabs value={productsFilter} onValueChange={setProductsFilter} className="w-auto">
                    <TabsList className="h-9 p-1">
                      <TabsTrigger value="all" className="text-xs py-1.5 px-3">
                        All
                      </TabsTrigger>
                      <TabsTrigger 
                        value="new" 
                        className="text-xs py-1.5 px-3"
                        disabled={newProductsCount === 0}
                      >
                        New {newProductsCount > 0 && (
                          <Badge variant="default" className="ml-1.5 text-[10px] px-1 py-0 h-4 bg-blue-500">
                            {newProductsCount}
                          </Badge>
                        )}
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </>
              )}
              <div className="flex items-center gap-2 flex-1 justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 px-3"
                  onClick={downloadCSV}
                  disabled={customersLoading || productsLoading || (activeTab === 'customers' ? customers.length === 0 : products.length === 0)}
                >
                  <Download className="h-3.5 w-3.5" />
                </Button>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 px-3"
                    >
                      <Columns className="h-3.5 w-3.5" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-64 p-0" align="end">
                    <div className="p-3 space-y-3">
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <h4 className="text-sm font-semibold">Columns</h4>
                          <div className="flex items-center gap-1">
                            {activeTab === 'customers' ? (
                              !areAllCustomerColumnsSelected() && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs"
                                  onClick={selectAllCustomerColumns}
                                >
                                  Select All
                                </Button>
                              )
                            ) : (
                              !areAllProductColumnsSelected() && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs"
                                  onClick={selectAllProductColumns}
                                >
                                  Select All
                                </Button>
                              )
                            )}
                            {activeTab === 'customers' ? (
                              !isOnlyNameVisibleForCustomers() && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs"
                                  onClick={deselectAllCustomerColumns}
                                >
                                  Deselect All
                                </Button>
                              )
                            ) : (
                              !isOnlyNameVisibleForProducts() && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 px-2 text-xs"
                                  onClick={deselectAllProductColumns}
                                >
                                  Deselect All
                                </Button>
                              )
                            )}
                          </div>
                        </div>
                        <div className="relative">
                          <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                          <Input
                            placeholder="Search columns..."
                            value={columnSearch}
                            onChange={(e) => setColumnSearch(e.target.value)}
                            className="pl-7 h-8 text-xs"
                          />
                        </div>
                      </div>
                      <div className="max-h-64 overflow-y-auto space-y-2">
                        {activeTab === 'customers' ? (
                          getFilteredCustomerColumns().length > 0 ? (
                            getFilteredCustomerColumns().map((column) => {
                              const isVisible = visibleCustomerColumns.has(column) || column === 'Name';
                              const isName = column === 'Name';
                              return (
                                <div key={column} className="flex items-center space-x-2">
                                  <Checkbox
                                    id={`customer-col-${column}`}
                                    checked={isVisible}
                                    onCheckedChange={() => toggleCustomerColumn(column)}
                                    disabled={isName}
                                  />
                                  <label
                                    htmlFor={`customer-col-${column}`}
                                    className={`text-xs cursor-pointer flex-1 ${
                                      isName ? 'text-muted-foreground' : ''
                                    }`}
                                  >
                                    {column}
                                  </label>
                                </div>
                              );
                            })
                          ) : (
                            <div className="text-xs text-muted-foreground text-center py-2">
                              No columns found
                            </div>
                          )
                        ) : (
                          getFilteredProductColumns().length > 0 ? (
                            getFilteredProductColumns().map((column) => {
                              const isVisible = visibleProductColumns.has(column) || column === 'Name';
                              const isName = column === 'Name';
                              return (
                                <div key={column} className="flex items-center space-x-2">
                                  <Checkbox
                                    id={`product-col-${column}`}
                                    checked={isVisible}
                                    onCheckedChange={() => toggleProductColumn(column)}
                                    disabled={isName}
                                  />
                                  <label
                                    htmlFor={`product-col-${column}`}
                                    className={`text-xs cursor-pointer flex-1 ${
                                      isName ? 'text-muted-foreground' : ''
                                    }`}
                                  >
                                    {column}
                                  </label>
                                </div>
                              );
                            })
                          ) : (
                            <div className="text-xs text-muted-foreground text-center py-2">
                              No columns found
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 px-3"
                  onClick={refreshCache}
                  disabled={refreshingCache || customersLoading || productsLoading}
                >
                  {refreshingCache ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
        <TabsContent value="customers" ref={customersTabContentRef} className="mt-0 flex-1 flex flex-col min-h-0 px-6 pb-6 data-[state=inactive]:hidden">
          <div className="flex-1 flex flex-col min-h-0 relative">
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
              <div className="flex-1 overflow-hidden border-[1px] rounded-md bg-white flex flex-col min-h-0 relative" id="customers-table-wrapper" style={{ width: '100%', maxWidth: '100%' }}>
                <div className="flex-1 overflow-auto" id="customers-scroll-container" style={{ width: '100%', maxWidth: '100%' }}>
                  <Table className="border-0 border-separate border-spacing-0">
                      <TableHeader className="bg-white">
                        <TableRow className="bg-white">
                          {customersFilter === 'new' && (
                            <TableHead 
                              className="text-xs font-semibold text-center sticky left-0 top-0 z-30 bg-white h-8 py-1"
                              style={{ 
                                position: 'sticky',
                                left: 0,
                                top: 0,
                                zIndex: 31,
                                backgroundColor: '#ffffff',
                                width: '60px',
                                minWidth: '60px',
                                maxWidth: '60px'
                              }}
                            >
                              Review
                            </TableHead>
                          )}
                          {customerColumns.map((column, colIdx) => {
                            const isNameColumn = column === 'Name';
                            const nameLeftOffset = customersFilter === 'new' ? '60px' : '0';
                            return (
                              <TableHead 
                                key={column} 
                                className={`text-xs font-semibold whitespace-nowrap h-8 py-1 ${
                                  isNameColumn 
                                    ? 'border-r-2 border-gray-200' 
                                    : ''
                                }`}
                                style={isNameColumn ? { 
                                  position: 'sticky',
                                  left: nameLeftOffset,
                                  top: 0,
                                  zIndex: 30,
                                  backgroundColor: '#ffffff',
                                  borderRightColor: '#e5e7eb'
                                } : { 
                                  position: 'sticky',
                                  top: 0,
                                  zIndex: 2,
                                  backgroundColor: '#ffffff'
                                }}
                              >
                                {column}
                              </TableHead>
                            );
                          })}
                        </TableRow>
                      </TableHeader>
                      <TableBody style={{ '--tw-border-opacity': '1' }} className="[&_tr]:border-b [&_tr:last-child]:!border-b [&_tr:last-child]:border-gray-200 [&_tr:last-child_td]:!border-b [&_tr:last-child_td]:border-gray-200">
                        {customers
                          .filter(customer => customersFilter === 'all' || customer._is_new)
                          .map((customer, idx, arr) => {
                          const isNew = customer._is_new;
                          const cacheId = customer._cache_id;
                          const nameLeftOffset = customersFilter === 'new' ? '60px' : '0';
                          const isLastRow = idx === arr.length - 1;
                          return (
                            <TableRow key={idx} className="border-b" style={{ borderBottom: '1px solid #e5e7eb !important' }}>
                              {customersFilter === 'new' && (
                                <TableCell 
                                  className="text-xs text-center sticky left-0 bg-white z-10 cursor-pointer"
                                  style={{ 
                                    position: 'sticky',
                                    left: 0,
                                    zIndex: 11,
                                    backgroundColor: '#ffffff',
                                    width: '60px',
                                    minWidth: '60px',
                                    maxWidth: '60px'
                                  }}
                                  onClick={() => isNew && markAsReviewed(cacheId, 'customer')}
                                  title={isNew ? 'Click to mark as reviewed' : 'Reviewed'}
                                >
                                  {isNew ? (
                                    <Circle className="h-4 w-4 text-muted-foreground hover:text-blue-500 mx-auto" />
                                  ) : (
                                    <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                                  )}
                                </TableCell>
                              )}
                              {customerColumns.map((column, colIdx) => {
                                const isNameColumn = column === 'Name';
                                return (
                                  <TableCell 
                                    key={column} 
                                    className={`text-xs whitespace-nowrap ${
                                      isNameColumn 
                                        ? 'sticky bg-white z-10 border-r-2 border-gray-200' 
                                        : ''
                                    }`}
                                    style={isNameColumn ? { 
                                      left: nameLeftOffset,
                                      borderRightColor: '#e5e7eb'
                                    } : {}}
                                  >
                                    {isNameColumn && customer._is_new ? (
                                      <div className="flex items-center gap-2">
                                        <span>{formatValue(customer[column])}</span>
                                        <Badge variant="default" className="text-[10px] px-1.5 py-0 h-4 bg-blue-500">
                                          New
                                        </Badge>
                                      </div>
                                    ) : (
                                      formatValue(customer[column])
                                    )}
                                  </TableCell>
                                );
                              })}
                            </TableRow>
                          );
                        })}
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
          <div className="flex-1 flex flex-col min-h-0 relative">
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
              <div className="flex-1 overflow-hidden border-[1px] rounded-md bg-white flex flex-col min-h-0 relative">
                <div className="flex-1 overflow-auto">
                  <Table className="border-0 border-separate border-spacing-0">
                      <TableHeader className="bg-white">
                        <TableRow className="bg-white">
                          {productsFilter === 'new' && (
                            <TableHead 
                              className="text-xs font-semibold text-center sticky left-0 top-0 z-30 bg-white h-8 py-1"
                              style={{ 
                                position: 'sticky',
                                left: 0,
                                top: 0,
                                zIndex: 31,
                                backgroundColor: '#ffffff',
                                width: '60px',
                                minWidth: '60px',
                                maxWidth: '60px'
                              }}
                            >
                              Review
                            </TableHead>
                          )}
                          {productColumns.map((column, colIdx) => {
                            const isNameColumn = column === 'Name';
                            const nameLeftOffset = productsFilter === 'new' ? '60px' : '0';
                            return (
                              <TableHead 
                                key={column} 
                                className={`text-xs font-semibold whitespace-nowrap h-8 py-1 ${
                                  isNameColumn 
                                    ? 'border-r-2 border-gray-200' 
                                    : ''
                                }`}
                                style={isNameColumn ? { 
                                  position: 'sticky',
                                  left: nameLeftOffset,
                                  top: 0,
                                  zIndex: 30,
                                  backgroundColor: '#ffffff',
                                  borderRightColor: '#e5e7eb'
                                } : { 
                                  position: 'sticky',
                                  top: 0,
                                  zIndex: 2,
                                  backgroundColor: '#ffffff'
                                }}
                              >
                                {column}
                              </TableHead>
                            );
                          })}
                        </TableRow>
                      </TableHeader>
                      <TableBody style={{ '--tw-border-opacity': '1' }} className="[&_tr]:border-b [&_tr:last-child]:!border-b [&_tr:last-child]:border-gray-200 [&_tr:last-child_td]:!border-b [&_tr:last-child_td]:border-gray-200">
                        {products
                          .filter(product => productsFilter === 'all' || product._is_new)
                          .map((product, idx, arr) => {
                          const isNew = product._is_new;
                          const cacheId = product._cache_id;
                          const nameLeftOffset = productsFilter === 'new' ? '60px' : '0';
                          const isLastRow = idx === arr.length - 1;
                          return (
                            <TableRow key={idx} className="border-b" style={{ borderBottom: '1px solid #e5e7eb !important' }}>
                              {productsFilter === 'new' && (
                                <TableCell 
                                  className="text-xs text-center sticky left-0 bg-white z-10 cursor-pointer"
                                  style={{ 
                                    position: 'sticky',
                                    left: 0,
                                    zIndex: 11,
                                    backgroundColor: '#ffffff',
                                    width: '60px',
                                    minWidth: '60px',
                                    maxWidth: '60px'
                                  }}
                                  onClick={() => isNew && markAsReviewed(cacheId, 'product')}
                                  title={isNew ? 'Click to mark as reviewed' : 'Reviewed'}
                                >
                                  {isNew ? (
                                    <Circle className="h-4 w-4 text-muted-foreground hover:text-blue-500 mx-auto" />
                                  ) : (
                                    <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                                  )}
                                </TableCell>
                              )}
                              {productColumns.map((column, colIdx) => {
                                const isNameColumn = column === 'Name';
                                return (
                                  <TableCell 
                                    key={column} 
                                    className={`text-xs whitespace-nowrap ${
                                      isNameColumn 
                                        ? 'sticky bg-white z-10 border-r-2 border-gray-200' 
                                        : ''
                                    }`}
                                    style={isNameColumn ? { 
                                      left: nameLeftOffset,
                                      borderRightColor: '#e5e7eb'
                                    } : {}}
                                  >
                                    {isNameColumn && product._is_new ? (
                                      <div className="flex items-center gap-2">
                                        <span>{formatValue(product[column])}</span>
                                        <Badge variant="default" className="text-[10px] px-1.5 py-0 h-4 bg-blue-500">
                                          New
                                        </Badge>
                                      </div>
                                    ) : (
                                      formatValue(product[column])
                                    )}
                                  </TableCell>
                                );
                              })}
                            </TableRow>
                          );
                        })}
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

