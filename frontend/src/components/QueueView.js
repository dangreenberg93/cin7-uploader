import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { useClient } from '../contexts/ClientContext';
import { useConnection } from '../contexts/ConnectionContext';
import { useActivityLog } from '../contexts/ActivityLogContext';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Checkbox } from './ui/checkbox';
import { Input } from './ui/input';
import { ChevronDown, ChevronRight, RefreshCw, CheckCircle2, XCircle, FileText, RotateCcw, Eye, Download, Code, AlertCircle, Circle, Check, ArrowUp, ArrowDown, Search, Upload, Loader2 } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip';
import { cn } from '../lib/utils';

const QueueView = () => {
  const { selectedClientId } = useClient();
  const { setConnected, setCredentials, setTestConnection } = useConnection();
  const { addTerminalLine } = useActivityLog();
  const location = useLocation();
  const navigate = useNavigate();
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [expandedUploads, setExpandedUploads] = useState(new Set());
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [csvContent, setCsvContent] = useState('');
  const [csvFilename, setCsvFilename] = useState('');
  const [viewingUploadId, setViewingUploadId] = useState(null);
  const [csvRows, setCsvRows] = useState([]);
  const [csvHeaders, setCsvHeaders] = useState([]);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [viewingOrderPayload, setViewingOrderPayload] = useState(null);
  const [apiLogs, setApiLogs] = useState([]);
  const [loadingApiLogs, setLoadingApiLogs] = useState(false);
  const [expandedLogIds, setExpandedLogIds] = useState(new Set());
  
  // Review notes modal state
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewModalOrderId, setReviewModalOrderId] = useState(null);
  const [reviewModalOrderType, setReviewModalOrderType] = useState(null); // Only used for 'failed' orders
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewNotesPreset, setReviewNotesPreset] = useState('');
  const [bulkReviewOrders, setBulkReviewOrders] = useState([]);
  const [bulkReviewIndex, setBulkReviewIndex] = useState(0);
  const [bulkReviewModalOpen, setBulkReviewModalOpen] = useState(false);
  
  // Failed Orders tab state
  const [failedOrders, setFailedOrders] = useState([]);
  const [failedOrdersLoading, setFailedOrdersLoading] = useState(true);
  const [isFailedOrdersInitialLoad, setIsFailedOrdersInitialLoad] = useState(true);
  const [selectedOrderIds, setSelectedOrderIds] = useState(new Set());
  const [errorTypeFilter, setErrorTypeFilter] = useState('');
  const [expandedFailedOrders, setExpandedFailedOrders] = useState(new Set());
  
  // Completed Orders tab state
  const [completedOrders, setCompletedOrders] = useState([]);
  const [completedOrdersLoading, setCompletedOrdersLoading] = useState(true);
  const [isCompletedOrdersInitialLoad, setIsCompletedOrdersInitialLoad] = useState(true);
  const [expandedCompletedOrders, setExpandedCompletedOrders] = useState(new Set());
  const [unreviewedCount, setUnreviewedCount] = useState(0);
  const [unreviewedFailedCount, setUnreviewedFailedCount] = useState(0);
  
  // Global filter and sort state
  const [searchQuery, setSearchQuery] = useState('');
  const [dateSortDirection, setDateSortDirection] = useState(null); // 'asc', 'desc', or null
  const [reviewFilterTab, setReviewFilterTab] = useState('all'); // 'needs-review' or 'all' for completed orders
  const [failedFilterTab, setFailedFilterTab] = useState('needs-review'); // 'needs-review' or 'all' for failed orders
  const [activeTab, setActiveTab] = useState('completed'); // 'completed', 'failed', or 'uploads'
  
  // File upload state
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  // Filter and sort uploads
  const filteredAndSortedUploads = useMemo(() => {
    let filtered = [...uploads];
    
    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      filtered = filtered.filter(upload => {
        const filename = (upload.filename || '').toLowerCase();
        const hasMatchingOrder = upload.order_results?.some(order => {
          const orderKey = (order.order_key || '').toLowerCase();
          const customerName = ((order.customer_name || 
            (order.sale_payload && (order.sale_payload.Customer || order.sale_payload.customer_name)) ||
            (order.sale_order_payload && (order.sale_order_payload.Customer || order.sale_order_payload.customer_name))) || '').toLowerCase();
          return orderKey.includes(query) || customerName.includes(query);
        });
        return filename.includes(query) || hasMatchingOrder;
      });
    }
    
    // Apply date sort
    if (dateSortDirection) {
      filtered.sort((a, b) => {
        const dateA = new Date(a.created_at || 0).getTime();
        const dateB = new Date(b.created_at || 0).getTime();
        return dateSortDirection === 'asc' ? dateA - dateB : dateB - dateA;
      });
    }
    
    return filtered;
  }, [uploads, searchQuery, dateSortDirection]);

  // Filter and sort failed orders
  const filteredAndSortedFailedOrders = useMemo(() => {
    let filtered = [...failedOrders];
    
    // Apply review filter (show only unreviewed orders)
    if (failedFilterTab === 'needs-review') {
      filtered = filtered.filter(order => !order.resolved_at);
    }
    
    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      filtered = filtered.filter(order => {
        const orderKey = (order.order_key || '').toLowerCase();
        const customerName = ((order.customer_name || 
          (order.sale_payload && (order.sale_payload.Customer || order.sale_payload.customer_name))) || '').toLowerCase();
        const poNumber = (order.po_number || '').toLowerCase();
        return orderKey.includes(query) || customerName.includes(query) || poNumber.includes(query);
      });
    }
    
    // Apply date sort (using last_retry_at or created_at if available)
    if (dateSortDirection) {
      filtered.sort((a, b) => {
        const dateA = new Date(a.last_retry_at || a.created_at || 0).getTime();
        const dateB = new Date(b.last_retry_at || b.created_at || 0).getTime();
        return dateSortDirection === 'asc' ? dateA - dateB : dateB - dateA;
      });
    }
    
    return filtered;
  }, [failedOrders, failedFilterTab, searchQuery, dateSortDirection]);

  // Filter and sort completed orders
  const filteredAndSortedCompletedOrders = useMemo(() => {
    let filtered = [...completedOrders];
    
    // Apply review filter (show only unreviewed orders)
    if (reviewFilterTab === 'needs-review') {
      filtered = filtered.filter(order => !order.reviewed);
    }
    
    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      filtered = filtered.filter(order => {
        const orderKey = (order.order_key || '').toLowerCase();
        const customerName = ((order.customer_name || 
          (order.sale_payload && (order.sale_payload.Customer || order.sale_payload.customer_name))) || '').toLowerCase();
        const poNumber = ((order.po_number || 
          (order.sale_payload && (order.sale_payload.CustomerReference || order.sale_payload.customer_reference))) || '').toLowerCase();
        return orderKey.includes(query) || customerName.includes(query) || poNumber.includes(query);
      });
    }
    
    // Apply date sort (using processed_at)
    if (dateSortDirection) {
      filtered.sort((a, b) => {
        const dateA = new Date(a.processed_at || 0).getTime();
        const dateB = new Date(b.processed_at || 0).getTime();
        return dateSortDirection === 'asc' ? dateA - dateB : dateB - dateA;
      });
    }
    
    return filtered;
  }, [completedOrders, reviewFilterTab, searchQuery, dateSortDirection]);

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

  const loadQueue = async (isRefresh = false) => {
    if (!selectedClientId) {
      setUploads([]);
      setLoading(false);
      return;
    }
    try {
      if (!isRefresh) {
        setLoading(true);
      }
      const response = await axios.get(`/webhooks/queue?client_id=${selectedClientId}`);
      setUploads(response.data.uploads || []);
      if (isInitialLoad) {
        setIsInitialLoad(false);
      }
    } catch (error) {
      console.error('Failed to load sales orders:', error);
      if (error.response?.status === 401) {
        toast.error('Please log in to view sales orders');
      } else {
        toast.error(`Failed to load sales orders: ${error.response?.data?.error || error.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadApiLogs = useCallback(async (orderId) => {
    if (!orderId) {
      console.warn('loadApiLogs called without orderId');
      setApiLogs([]);
      return;
    }
    
    try {
      setLoadingApiLogs(true);
      console.log('Loading API logs for order:', orderId);
      const response = await axios.get(`/webhooks/orders/${orderId}/api-logs`);
      console.log('API logs response:', response.data);
      console.log('Number of logs:', response.data.logs?.length || 0);
      console.log('Upload ID from response:', response.data.upload_id);
      setApiLogs(response.data.logs || []);
    } catch (error) {
      console.error('Failed to load API logs:', error);
      console.error('Error response:', error.response?.data);
      console.error('Error status:', error.response?.status);
      setApiLogs([]);
      // Show error in console but don't show toast
    } finally {
      setLoadingApiLogs(false);
    }
  }, []);

  // Load API logs when modal opens with an order or upload
  useEffect(() => {
    if (jsonModalOpen && viewingOrderPayload) {
      let orderId = null;
      
      // Check if this is an upload object (has order_results as direct property)
      // Uploads are passed as { upload, order_results }
      // Orders are passed directly and have properties like sale_payload, id, etc.
      if (viewingOrderPayload.order_results && Array.isArray(viewingOrderPayload.order_results)) {
        // This is an upload - use the first order_result's ID to load logs
        // (the endpoint returns all logs for the upload anyway)
        if (viewingOrderPayload.order_results.length > 0) {
          orderId = viewingOrderPayload.order_results[0].id;
        }
      } else {
        // This is an order - try different possible ID fields
        // Check multiple possible locations for the ID
        orderId = viewingOrderPayload.id || 
                   viewingOrderPayload.order_result_id ||
                   viewingOrderPayload.order_id ||
                   (viewingOrderPayload.order_data && viewingOrderPayload.order_data.id);
        
        // If still no ID, check if it's a string UUID that needs parsing
        if (!orderId && typeof viewingOrderPayload === 'object') {
          // Try to find any UUID-like string in the object
          const findId = (obj) => {
            if (!obj || typeof obj !== 'object') return null;
            for (const [key, value] of Object.entries(obj)) {
              if (key.toLowerCase().includes('id') && value) {
                if (typeof value === 'string' && value.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
                  return value;
                }
                if (typeof value === 'string' && value.length === 36) {
                  return value;
                }
              }
              if (typeof value === 'object' && value !== null) {
                const found = findId(value);
                if (found) return found;
              }
            }
            return null;
          };
          orderId = findId(viewingOrderPayload);
        }
      }
      
      console.log('Modal opened with order payload:', viewingOrderPayload);
      console.log('Extracted order ID:', orderId);
      console.log('Available keys in viewingOrderPayload:', Object.keys(viewingOrderPayload || {}));
      console.log('Order status:', viewingOrderPayload?.status || viewingOrderPayload?.order_data?.status);
      console.log('Order has id field:', !!viewingOrderPayload?.id);
      console.log('Order id value:', viewingOrderPayload?.id);
      
      if (orderId) {
        console.log('Calling loadApiLogs with orderId:', orderId);
        loadApiLogs(orderId);
      } else {
        console.warn('No order ID found in viewingOrderPayload. Available keys:', Object.keys(viewingOrderPayload || {}));
        console.warn('Full viewingOrderPayload:', JSON.stringify(viewingOrderPayload, null, 2));
        setApiLogs([]);
        setLoadingApiLogs(false);
      }
    } else {
      setApiLogs([]);
      setLoadingApiLogs(false);
    }
  }, [jsonModalOpen, viewingOrderPayload, loadApiLogs]);

  const loadFailedOrders = async (isRefresh = false) => {
    if (!selectedClientId) {
      setFailedOrders([]);
      setFailedOrdersLoading(false);
      return;
    }
    try {
      if (!isRefresh) {
        setFailedOrdersLoading(true);
      }
      // Load all failed orders (both reviewed and unreviewed) so we can filter in the UI
      const response = await axios.get(`/webhooks/orders/failed?include_resolved=true&client_id=${selectedClientId}`);
      setFailedOrders(response.data.failed_orders || []);
      if (isFailedOrdersInitialLoad) {
        setIsFailedOrdersInitialLoad(false);
      }
    } catch (error) {
      console.error('Failed to load failed orders:', error);
      if (error.response?.status === 401) {
        toast.error('Please log in to view failed orders');
      } else {
        toast.error(`Failed to load failed orders: ${error.response?.data?.error || error.message}`);
      }
    } finally {
      setFailedOrdersLoading(false);
    }
  };

  const loadUnreviewedFailedCount = async () => {
    if (!selectedClientId) {
      setUnreviewedFailedCount(0);
      return;
    }
    try {
      const response = await axios.get(`/webhooks/orders/failed/unreviewed-count?client_id=${selectedClientId}`);
      const count = response.data.unreviewed_count || 0;
      setUnreviewedFailedCount(count);
      // Set default tab based on unreviewed count (only on initial load or if currently on needs-review with 0 count)
      setFailedFilterTab(prev => {
        if (count > 0 && prev === 'all') {
          return 'needs-review';
        } else if (count === 0 && prev === 'needs-review') {
          return 'all';
        }
        return prev;
      });
    } catch (error) {
      console.error('Failed to load unreviewed failed count:', error);
      // Don't show error toast for this, just log it
    }
  };

  const loadCompletedOrders = async (isRefresh = false) => {
    if (!selectedClientId) {
      setCompletedOrders([]);
      setCompletedOrdersLoading(false);
      return;
    }
    try {
      if (!isRefresh) {
        setCompletedOrdersLoading(true);
      }
      const response = await axios.get(`/webhooks/orders/completed?client_id=${selectedClientId}`);
      setCompletedOrders(response.data.completed_orders || []);
      if (isCompletedOrdersInitialLoad) {
        setIsCompletedOrdersInitialLoad(false);
      }
    } catch (error) {
      console.error('Failed to load completed orders:', error);
      if (error.response?.status === 401) {
        toast.error('Please log in to view completed orders');
      } else {
        toast.error(`Failed to load completed orders: ${error.response?.data?.error || error.message}`);
      }
    } finally {
      setCompletedOrdersLoading(false);
    }
  };

  const loadUnreviewedCount = async () => {
    if (!selectedClientId) {
      setUnreviewedCount(0);
      return;
    }
    try {
      const response = await axios.get(`/webhooks/orders/completed/unreviewed-count?client_id=${selectedClientId}`);
      const count = response.data.unreviewed_count || 0;
      setUnreviewedCount(count);
      // Set default tab based on unreviewed count (only on initial load or if currently on needs-review with 0 count)
      setReviewFilterTab(prev => {
        if (count > 0 && prev === 'all') {
          return 'needs-review';
        } else if (count === 0 && prev === 'needs-review') {
          return 'all';
        }
        return prev;
      });
    } catch (error) {
      console.error('Failed to load unreviewed count:', error);
      // Don't show error toast for this, just log it
    }
  };

  const openReviewModal = (orderId, orderType) => {
    setReviewModalOrderId(orderId);
    setReviewModalOrderType(orderType);
    setReviewNotes('');
    setReviewNotesPreset('');
    setReviewModalOpen(true);
  };

  const submitReview = async () => {
    if (!reviewNotes.trim()) {
      toast.error('Please enter review notes');
      return;
    }

    try {
      // Only handle failed orders (review_notes only required for failed orders)
      await axios.post(`/webhooks/orders/${reviewModalOrderId}/resolve`, { 
        review_notes: reviewNotes 
      });
      
      // Update the order in local state
      setFailedOrders(prevOrders => 
        prevOrders.map(order => 
          order.id === reviewModalOrderId 
            ? { ...order, resolved_at: new Date().toISOString(), review_notes: reviewNotes }
            : order
        )
      );
      setUnreviewedFailedCount(prev => {
        const newCount = Math.max(0, prev - 1);
        if (newCount === 0 && failedFilterTab === 'needs-review') {
          setFailedFilterTab('all');
        }
        return newCount;
      });
      
      toast.success('Order marked as reviewed');
      setReviewModalOpen(false);
      setReviewNotes('');
      setReviewNotesPreset('');
      
      // Notify sidebar to refresh counts immediately
      window.dispatchEvent(new CustomEvent('refreshSidebarCounts'));
    } catch (error) {
      console.error('Failed to update order reviewed status:', error);
      toast.error(error.response?.data?.error || 'Failed to update order reviewed status');
    }
  };

  const markOrderAsReviewed = async (orderId, reviewed) => {
    try {
      await axios.post(`/webhooks/orders/${orderId}/review`, { reviewed });
      // Update the order in local state
      setCompletedOrders(prevOrders => 
        prevOrders.map(order => 
          order.id === orderId ? { ...order, reviewed } : order
        )
      );
      // Update the unreviewed count
      if (reviewed) {
        setUnreviewedCount(prev => {
          const newCount = Math.max(0, prev - 1);
          // If we're on "needs-review" tab and count becomes 0, switch to "all"
          if (newCount === 0 && reviewFilterTab === 'needs-review') {
            setReviewFilterTab('all');
          }
          return newCount;
        });
        toast.success('Order marked as reviewed');
      } else {
        setUnreviewedCount(prev => prev + 1);
        toast.success('Order marked as unreviewed');
      }
      
      // Notify sidebar to refresh counts immediately
      window.dispatchEvent(new CustomEvent('refreshSidebarCounts'));
    } catch (error) {
      console.error('Failed to update order reviewed status:', error);
      toast.error(error.response?.data?.error || 'Failed to update order reviewed status');
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([
        loadQueue(true),
        loadFailedOrders(true),
        loadCompletedOrders(true),
        loadUnreviewedCount(),
        loadUnreviewedFailedCount()
      ]);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Handle URL params for tab navigation
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const tab = params.get('tab');
    const review = params.get('review');
    
    if (tab === 'failed') {
      setActiveTab('failed');
      if (review === 'all') {
        setFailedFilterTab('all');
      } else {
        setFailedFilterTab('needs-review');
      }
    } else if (tab === 'completed') {
      setActiveTab('completed');
      if (review === 'needs-review') {
        setReviewFilterTab('needs-review');
      }
    } else if (tab === 'uploads') {
      setActiveTab('uploads');
    }
  }, [location.search]);

  // Use ref to track latest uploads
  const uploadsRef = useRef(uploads);
  const previousProcessingStateRef = useRef(false);
  
  useEffect(() => {
    uploadsRef.current = uploads;
    
    // Check if processing state changed and notify sidebar
    const hasProcessingUpload = uploads.some(upload => upload.status === 'processing');
    if (hasProcessingUpload !== previousProcessingStateRef.current) {
      previousProcessingStateRef.current = hasProcessingUpload;
      window.dispatchEvent(new CustomEvent('uploadProcessingStateChange', {
        detail: { isLiveMode: hasProcessingUpload }
      }));
    }
  }, [uploads]);

  useEffect(() => {
    if (!selectedClientId) return;
    
    // Initial load
    loadQueue();
    loadFailedOrders();
    loadCompletedOrders();
    loadUnreviewedCount();
    loadUnreviewedFailedCount();
    
    // Connect to Server-Sent Events for real-time updates
    // Note: EventSource doesn't support custom headers, so we pass token as query param
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn('No token found, skipping SSE connection');
      return;
    }
    
    // Build SSE URL - handle both absolute and relative baseURL
    let sseUrl = '/api/webhooks/events';
    if (axios.defaults.baseURL) {
      if (axios.defaults.baseURL.startsWith('http')) {
        sseUrl = `${axios.defaults.baseURL}/webhooks/events`;
      } else {
        sseUrl = `${axios.defaults.baseURL}/webhooks/events`;
      }
    }
    sseUrl += `?token=${encodeURIComponent(token)}`;
    const eventSource = new EventSource(sseUrl);
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'upload_status_changed') {
          // Refresh all data when upload status changes
          loadQueue(true);
          loadFailedOrders(true);
          loadCompletedOrders(true);
          loadUnreviewedCount();
          loadUnreviewedFailedCount();
          
          // Notify sidebar to refresh counts
          window.dispatchEvent(new CustomEvent('refreshSidebarCounts'));
        }
      } catch (error) {
        console.error('Error parsing SSE event:', error);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      // EventSource will automatically reconnect
    };
    
    // Fallback polling every 60 seconds in case SSE connection fails
    const fallbackInterval = setInterval(() => {
      loadQueue(true);
      loadFailedOrders(true);
      loadCompletedOrders(true);
      loadUnreviewedCount();
      loadUnreviewedFailedCount();
    }, 60000);
    
    return () => {
      eventSource.close();
      clearInterval(fallbackInterval);
    };
  }, [selectedClientId]);


  const toggleExpand = (uploadId) => {
    const newExpanded = new Set(expandedUploads);
    if (newExpanded.has(uploadId)) {
      newExpanded.delete(uploadId);
    } else {
      newExpanded.add(uploadId);
    }
    setExpandedUploads(newExpanded);
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'processing':
        return (
          <div className="flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
            <span className="text-xs text-blue-500 font-medium">Processing</span>
          </div>
        );
      case 'completed':
      case 'failed':
      case 'duplicate':
      default:
        // All non-processing statuses show as "Processed"
        return <Badge variant="default" className="bg-gray-500 shadow-none hover:bg-gray-500 px-1.5 py-0 text-[10px] text-white">Processed</Badge>;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    // Format as local date and time
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });
  };

  const retryOrder = async (orderResultId) => {
    try {
      const response = await axios.post(`/webhooks/retry/${orderResultId}`);
      if (response.data.status === 'success') {
        toast.success('Order retried successfully!');
        loadQueue(true);
        loadFailedOrders(true);
      } else {
        toast.error(`Retry failed: ${response.data.error_message || 'Unknown error'}`);
        loadQueue(true);
        loadFailedOrders(true);
      }
    } catch (error) {
      console.error('Failed to retry order:', error);
      toast.error(error.response?.data?.error || 'Failed to retry order');
    }
  };

  const bulkRetryOrders = async () => {
    if (selectedOrderIds.size === 0) {
      toast.error('Please select at least one order');
      return;
    }
    
    try {
      const response = await axios.post('/webhooks/orders/bulk-retry', {
        order_ids: Array.from(selectedOrderIds)
      });
      
      const results = response.data.results || [];
      const successful = results.filter(r => r.status === 'success').length;
      const failed = results.filter(r => r.status === 'error' || r.status === 'failed').length;
      
      if (successful > 0) {
        toast.success(`${successful} order(s) retried successfully`);
      }
      if (failed > 0) {
        toast.error(`${failed} order(s) failed to retry`);
      }
      
      setSelectedOrderIds(new Set());
      loadQueue(true);
      loadFailedOrders(true);
    } catch (error) {
      console.error('Failed to bulk retry orders:', error);
      toast.error(error.response?.data?.error || 'Failed to bulk retry orders');
    }
  };

  const resolveOrder = async (orderId, reason = '') => {
    try {
      await axios.post(`/webhooks/orders/${orderId}/resolve`, { reason });
      // Update the order in local state
      setFailedOrders(prevOrders => 
        prevOrders.map(order => 
          order.id === orderId ? { ...order, resolved_at: new Date().toISOString() } : order
        )
      );
      // Update the unreviewed failed count
      setUnreviewedFailedCount(prev => {
        const newCount = Math.max(0, prev - 1);
        // If we're on "needs-review" tab and count becomes 0, switch to "all"
        if (newCount === 0 && failedFilterTab === 'needs-review') {
          setFailedFilterTab('all');
        }
        return newCount;
      });
      toast.success('Order marked as reviewed');
    } catch (error) {
      console.error('Failed to resolve order:', error);
      toast.error(error.response?.data?.error || 'Failed to review order');
    }
  };

  const markFailedOrderAsReviewed = async (orderId, reviewed) => {
    if (reviewed) {
      // Show modal for review notes
      openReviewModal(orderId, 'failed');
    } else {
      // Unmarking doesn't require notes
      try {
        await axios.post(`/webhooks/orders/${orderId}/resolve`, { unresolve: true });
        setFailedOrders(prevOrders => 
          prevOrders.map(order => 
            order.id === orderId ? { ...order, resolved_at: null, review_notes: null } : order
          )
        );
        setUnreviewedFailedCount(prev => prev + 1);
        toast.success('Order marked as unreviewed');
        window.dispatchEvent(new CustomEvent('refreshSidebarCounts'));
      } catch (error) {
        console.error('Failed to update order reviewed status:', error);
        toast.error(error.response?.data?.error || 'Failed to update order reviewed status');
      }
    }
  };

  const bulkResolveOrders = async () => {
    if (selectedOrderIds.size === 0) {
      toast.error('Please select at least one order');
      return;
    }
    
    // Get selected orders that aren't already resolved
    const ordersToReview = failedOrders.filter(o => 
      selectedOrderIds.has(o.id) && !o.resolved_at
    );
    
    if (ordersToReview.length === 0) {
      toast.error('No unreviewed orders selected');
      return;
    }
    
    // Start bulk review process
    setBulkReviewOrders(ordersToReview);
    setBulkReviewIndex(0);
    setReviewNotes('');
    setReviewNotesPreset('');
    setBulkReviewModalOpen(true);
  };

  const submitBulkReview = async () => {
    if (!reviewNotes.trim()) {
      toast.error('Please enter review notes');
      return;
    }

    const currentOrder = bulkReviewOrders[bulkReviewIndex];
    
    try {
      await axios.post(`/webhooks/orders/${currentOrder.id}/resolve`, { 
        review_notes: reviewNotes 
      });
      
      // Move to next order or finish
      if (bulkReviewIndex < bulkReviewOrders.length - 1) {
        setBulkReviewIndex(prev => prev + 1);
        setReviewNotes('');
        setReviewNotesPreset('');
      } else {
        // All orders reviewed
        const resolvedTime = new Date().toISOString();
        setFailedOrders(prevOrders => 
          prevOrders.map(order => 
            selectedOrderIds.has(order.id) && !order.resolved_at
              ? { ...order, resolved_at: resolvedTime, review_notes: reviewNotes }
              : order
          )
        );
        
        const reviewedCount = bulkReviewOrders.length;
        setUnreviewedFailedCount(prev => {
          const newCount = Math.max(0, prev - reviewedCount);
          if (newCount === 0 && failedFilterTab === 'needs-review') {
            setFailedFilterTab('all');
          }
          return newCount;
        });
        
        setSelectedOrderIds(new Set());
        setBulkReviewModalOpen(false);
        setReviewNotes('');
        setReviewNotesPreset('');
        toast.success(`${bulkReviewOrders.length} order(s) marked as reviewed`);
        window.dispatchEvent(new CustomEvent('refreshSidebarCounts'));
      }
    } catch (error) {
      console.error('Failed to review order:', error);
      toast.error(error.response?.data?.error || 'Failed to review order');
    }
  };

  const toggleSelectOrder = (orderId, checked) => {
    const newSelected = new Set(selectedOrderIds);
    if (checked) {
      newSelected.add(orderId);
    } else {
      newSelected.delete(orderId);
    }
    setSelectedOrderIds(newSelected);
  };

  const toggleSelectAll = (checked) => {
    // Use failedOrders directly since this is called from the table header
    // The filtered list is used for rendering, but we want to select all visible items
    if (checked) {
      setSelectedOrderIds(new Set(failedOrders.map(o => o.id)));
    } else {
      setSelectedOrderIds(new Set());
    }
  };

  const toggleExpandFailedOrder = (orderId) => {
    const newExpanded = new Set(expandedFailedOrders);
    if (newExpanded.has(orderId)) {
      newExpanded.delete(orderId);
    } else {
      newExpanded.add(orderId);
    }
    setExpandedFailedOrders(newExpanded);
  };

  const handleFileUpload = async (file) => {
    if (!selectedClientId) {
      toast.error('Please select a client first');
      return;
    }

    if (!file) {
      return;
    }

    // Validate file type
    if (!file.name.endsWith('.csv')) {
      toast.error('Please upload a CSV file');
      return;
    }

    setIsUploading(true);
    addTerminalLine('info', `Uploading file: ${file.name}`);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('client_id', selectedClientId);

      const response = await axios.post('/webhooks/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data.error) {
        toast.error(response.data.error);
        addTerminalLine('error', `Upload failed: ${response.data.error}`);
      } else {
        toast.success(`File uploaded successfully! Processing ${file.name}...`);
        addTerminalLine('success', `File uploaded: ${file.name}. Processing in background...`);
        
        // Refresh the queue after a short delay to show the new upload
        setTimeout(() => {
          loadQueue(true);
        }, 2000);
      }
    } catch (error) {
      console.error('Upload error:', error);
      const errorMessage = error.response?.data?.error || error.message || 'Failed to upload file';
      toast.error(errorMessage);
      addTerminalLine('error', `Upload failed: ${errorMessage}`);
    } finally {
      setIsUploading(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const getErrorTypeBadge = (errorType) => {
    if (!errorType) return null;
    
    const typeLabels = {
      'customer_not_found': 'Customer Not Found',
      'missing_fields': 'Missing Fields',
      'api_error': 'API Error',
      'validation_error': 'Validation Error',
      'duplicate_po': 'Duplicate PO',
      'partial_success': 'Partial Success'
    };
    
    const typeColors = {
      'customer_not_found': 'bg-red-500',
      'missing_fields': 'bg-orange-500',
      'api_error': 'bg-purple-500',
      'validation_error': 'bg-yellow-500',
      'duplicate_po': 'bg-blue-500',
      'partial_success': 'bg-orange-500'
    };
    
    return (
      <Badge className={cn(typeColors[errorType] || 'bg-gray-500', 'text-white text-[10px] px-1.5 py-0 h-4 font-semibold shadow-none hover:opacity-100')}>
        {typeLabels[errorType] || errorType}
      </Badge>
    );
  };

  const parseCsv = (csvText) => {
    if (!csvText) return { headers: [], rows: [] };
    
    const lines = csvText.split('\n').filter(line => line.trim());
    if (lines.length === 0) return { headers: [], rows: [] };
    
    // Parse CSV line (handles quoted values with commas)
    const parseCsvLine = (line) => {
      const result = [];
      let current = '';
      let inQuotes = false;
      
      for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
          inQuotes = !inQuotes;
        } else if (char === ',' && !inQuotes) {
          result.push(current.trim());
          current = '';
        } else {
          current += char;
        }
      }
      result.push(current.trim());
      return result;
    };
    
    const headers = parseCsvLine(lines[0]);
    const rows = lines.slice(1).map((line, idx) => ({
      rowNumber: idx + 2, // CSV row number (1-indexed, +1 for header)
      data: parseCsvLine(line)
    }));
    
    return { headers, rows };
  };

  const viewCsv = async (uploadId, filename) => {
    try {
      setViewingUploadId(uploadId);
      setCsvFilename(filename);
      const response = await axios.get(`/webhooks/upload/${uploadId}/csv`, {
        responseType: 'text'
      });
      setCsvContent(response.data);
      const parsed = parseCsv(response.data);
      setCsvHeaders(parsed.headers);
      setCsvRows(parsed.rows);
      setCsvModalOpen(true);
    } catch (error) {
      console.error('Failed to load CSV:', error);
      toast.error('Failed to load CSV file');
    }
  };

  const renderCsvLineItems = (allRows, matchingDetails = null, orderContext = null) => {
    if (!allRows || !Array.isArray(allRows) || allRows.length === 0) return null;
    
    // Find SKU, Quantity, and Price columns (case-insensitive)
    const findColumn = (row, possibleNames) => {
      for (const name of possibleNames) {
        const key = Object.keys(row).find(k => k.toLowerCase() === name.toLowerCase());
        if (key) return key;
      }
      return null;
    };
    
    // Helper to format currency with thousands separators
    const formatCurrency = (value) => {
      if (value === null || value === undefined || value === '-' || isNaN(Number(value))) return '-';
      return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };
    
    return (
      <TooltipProvider>
        <div className="space-y-3">
          <div>
            <div className="text-xs font-semibold text-gray-700 mb-1">Line Items</div>
            <div className="border-[1px] rounded-md overflow-hidden bg-white">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-gray-50">
                      <TableHead className="font-semibold text-xs">SKU</TableHead>
                      <TableHead className="font-semibold text-xs text-right">Quantity</TableHead>
                      <TableHead className="font-semibold text-xs text-right">Price</TableHead>
                      <TableHead className="font-semibold text-xs text-right">Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {allRows.map((row, idx) => {
                      const skuCol = findColumn(row, ['SKU', 'Item Code', 'ProductCode', 'sku', 'item_code', 'product_code']);
                      const qtyCol = findColumn(row, ['Quantity', 'Qty', 'quantity', 'qty']);
                      const priceCol = findColumn(row, ['Price', 'Unit Price', 'price', 'unit_price']);
                      
                      const sku = skuCol && row[skuCol] != null ? String(row[skuCol]) : '-';
                      const quantity = qtyCol && row[qtyCol] != null ? String(row[qtyCol]) : '-';
                      const price = priceCol && row[priceCol] != null ? String(row[priceCol]) : '-';
                      const total = (quantity !== '-' && price !== '-') 
                        ? formatCurrency(Number(quantity) * Number(price))
                        : '-';
                      
                      // Check if product was matched
                      const productMatch = matchingDetails?.products?.find(p => p.sku === sku);
                      const isMatched = productMatch?.found;
                      const isUnmatched = productMatch && !productMatch.found;
                      const productId = productMatch?.cin7_id || null;
                      
                      return (
                        <TableRow key={idx} className="bg-white">
                          <TableCell className="text-xs text-gray-900">
                            <div className="flex items-center gap-1.5">
                              <span>{sku || '-'}</span>
                              {isMatched && productId && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span className="inline-flex items-center justify-center rounded-full border border-transparent bg-green-500 hover:bg-green-600 cursor-help h-4 w-4">
                                      <Check className="h-2.5 w-2.5 text-white stroke-[3]" />
                                    </span>
                                  </TooltipTrigger>
                                  <TooltipContent className="bg-black text-white">
                                    <p className="text-xs">ID: {String(productId || 'N/A')}</p>
                                  </TooltipContent>
                                </Tooltip>
                              )}
                              {isUnmatched && (
                                <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-destructive font-sans">
                                  SKU Missing in Cin7
                                </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-right text-xs text-gray-900">{quantity}</TableCell>
                          <TableCell className="text-right text-xs text-gray-900">{price !== '-' ? `$${Number(price).toFixed(2)}` : '-'}</TableCell>
                          <TableCell className="text-right text-xs text-gray-900">{total}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>
          </div>
        </div>
      </TooltipProvider>
    );
  };

  const renderPayloadTable = (payload, title, showOrderHeader = false, matchingDetails = null, orderContext = null) => {
    console.log('🎨 renderPayloadTable called', { 
      title, 
      hasPayload: !!payload, 
      hasOrderContext: !!orderContext,
      orderContextKeys: orderContext ? Object.keys(orderContext) : [],
      hasOrderData: !!orderContext?.order_data,
      orderDataKeys: orderContext?.order_data ? Object.keys(orderContext.order_data) : []
    });
    
    if (!payload || typeof payload !== 'object') return null;
    
    // Helper function to find column in CSV row (same as in renderCsvLineItems)
    const findColumn = (row, possibleNames) => {
      if (!row || typeof row !== 'object') return null;
      for (const name of possibleNames) {
        const key = Object.keys(row).find(k => k.toLowerCase() === name.toLowerCase());
        if (key) return key;
      }
      return null;
    };
    
    // Helper to clean and parse numeric value (removes currency symbols, commas, etc.)
    const parseNumericValue = (value) => {
      if (value === null || value === undefined || value === '') return null;
      // Convert to string, remove currency symbols, commas, and whitespace
      const cleaned = String(value).replace(/[$,\s]/g, '').trim();
      const num = Number(cleaned);
      return isNaN(num) ? null : num;
    };
    
    // Helper to format currency with thousands separators
    const formatCurrency = (value) => {
      if (value === null || value === undefined || value === '-' || isNaN(Number(value))) return '-';
      return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };
    
    // Helper function to get CSV values for a line item
    const getCsvValuesForLine = (lineSku) => {
      console.log('🔍 getCsvValuesForLine called', { lineSku, hasOrderContext: !!orderContext });
      
      if (!lineSku) {
        console.log('❌ No lineSku provided');
        return null;
      }
      
      // Try multiple paths to get all_rows
      const allRows = orderContext?.order_data?.all_rows || 
                      (orderContext?.order_data && Array.isArray(orderContext.order_data.all_rows) ? orderContext.order_data.all_rows : null) ||
                      null;
      
      console.log('📊 all_rows check', {
        hasAllRows: !!allRows,
        isArray: Array.isArray(allRows),
        length: allRows?.length,
        orderContextKeys: orderContext ? Object.keys(orderContext) : [],
        orderDataKeys: orderContext?.order_data ? Object.keys(orderContext.order_data) : []
      });
      
      if (!allRows || !Array.isArray(allRows) || allRows.length === 0) {
        console.log('❌ No all_rows found', {
          hasOrderContext: !!orderContext,
          hasOrderData: !!orderContext?.order_data,
          orderDataKeys: orderContext?.order_data ? Object.keys(orderContext.order_data) : [],
          orderContextType: typeof orderContext,
          orderData: orderContext?.order_data
        });
        return null;
      }
      
      const columnMapping = orderContext?.order_data?.column_mapping || {};
      const searchSku = String(lineSku).trim().toLowerCase();
      
      // Get all possible SKU column names to try
      const skuMappingCol = columnMapping.SKU || columnMapping.sku || null;
      const possibleSkuColumns = skuMappingCol 
        ? [skuMappingCol, ...['SKU', 'Item Code', 'ProductCode', 'sku', 'item_code', 'product_code', 'ItemCode']]
        : ['SKU', 'Item Code', 'ProductCode', 'sku', 'item_code', 'product_code', 'ItemCode'];
      
      // Get all possible quantity and price column names
      const qtyMappingCol = columnMapping.Quantity || columnMapping.quantity || null;
      const possibleQtyColumns = qtyMappingCol
        ? [qtyMappingCol, ...['Quantity', 'Quantity Ordered', 'Qty', 'Qty Ordered', 'quantity', 'qty', 'QTY', 'QuantityOrdered', 'QtyOrdered']]
        : ['Quantity', 'Quantity Ordered', 'Qty', 'Qty Ordered', 'quantity', 'qty', 'QTY', 'QuantityOrdered', 'QtyOrdered'];
      
      const priceMappingCol = columnMapping.Price || columnMapping.price || null;
      const possiblePriceColumns = priceMappingCol
        ? [priceMappingCol, ...['Price', 'Unit Price', 'price', 'unit_price', 'UnitPrice', 'Unit_Price']]
        : ['Price', 'Unit Price', 'price', 'unit_price', 'UnitPrice', 'Unit_Price'];
      
      console.log('🔬 Starting row search', {
        searchSku,
        allRowsCount: allRows.length,
        firstRowKeys: allRows[0] ? Object.keys(allRows[0]) : [],
        firstRowSample: allRows[0] ? Object.entries(allRows[0]).slice(0, 10) : [],
        possibleSkuColumns,
        columnMapping
      });
      
      // Try each row
      for (let rowIdx = 0; rowIdx < allRows.length; rowIdx++) {
        const row = allRows[rowIdx];
        if (!row || typeof row !== 'object') {
          console.log(`⚠️ Row ${rowIdx} is invalid`, row);
          continue;
        }
        
        console.log(`🔍 Checking row ${rowIdx}`, {
          rowKeys: Object.keys(row),
          rowSample: Object.entries(row).slice(0, 10)
        });
        
        // Try to find SKU column and match value
        let matchedSku = false;
        for (const skuColName of possibleSkuColumns) {
          const skuValue = row[skuColName];
          if (skuValue != null) {
            const rowSku = String(skuValue).trim().toLowerCase();
            console.log(`  Comparing SKU: "${rowSku}" === "${searchSku}"`, { skuColName, skuValue });
            if (rowSku === searchSku) {
              matchedSku = true;
              console.log(`✅ SKU matched in row ${rowIdx}!`, { skuColName, row });
              
              // Found matching SKU, now get quantity and price
              // Use findColumn first for case-insensitive matching, then try exact match
              let qtyCol = findColumn(row, possibleQtyColumns);
              let priceCol = findColumn(row, possiblePriceColumns);
              
              // If findColumn didn't work, try exact matches
              if (!qtyCol) {
                for (const qtyColName of possibleQtyColumns) {
                  if (row.hasOwnProperty(qtyColName) && row[qtyColName] != null) {
                    qtyCol = qtyColName;
                    break;
                  }
                }
              }
              
              if (!priceCol) {
                for (const priceColName of possiblePriceColumns) {
                  if (row.hasOwnProperty(priceColName) && row[priceColName] != null) {
                    priceCol = priceColName;
                    break;
                  }
                }
              }
              
              const quantity = qtyCol && row[qtyCol] != null ? row[qtyCol] : null;
              const price = priceCol && row[priceCol] != null ? row[priceCol] : null;
              
              console.log(`📦 Found values for row ${rowIdx}`, {
                qtyCol,
                priceCol,
                quantity,
                price,
                quantityRaw: qtyCol ? row[qtyCol] : 'N/A',
                priceRaw: priceCol ? row[priceCol] : 'N/A',
                allRowValues: row
              });
              
              if (quantity != null || price != null) {
                console.log(`✅ Returning CSV values`, { quantity, price });
                return { quantity, price };
              }
              
              // If we matched SKU but couldn't find quantity/price, log it
              console.log('❌ Matched SKU but no quantity/price', {
                sku: lineSku,
                rowKeys: Object.keys(row),
                qtyCol,
                priceCol,
                possibleQtyColumns,
                possiblePriceColumns,
                rowValues: row
              });
            }
          }
        }
      }
      
      console.log('getCsvValuesForLine: SKU not found in all_rows', {
        searchSku,
        allRowsLength: allRows.length,
        firstRowKeys: allRows[0] ? Object.keys(allRows[0]) : [],
        firstRowSample: allRows[0] ? Object.entries(allRows[0]).slice(0, 5) : []
      });
      return null;
    };
    
    // For completed orders, check if sale was created (means customer was found)
    const isCompletedOrder = orderContext?.sale_id || orderContext?.sale_order_id;
    const customerIdInPayload = payload.CustomerID && typeof payload.CustomerID === 'string' && !payload.CustomerID.includes('<REQUIRED:');
    const customerWasFound = isCompletedOrder || customerIdInPayload;
    
    // Check if it's a sale_order_payload (has Lines array)
    if (payload.Lines && Array.isArray(payload.Lines)) {
      return (
        <TooltipProvider>
          <div className="space-y-3">
          {/* Order Details fields (non-Lines fields) - only show if showOrderHeader is true */}
          {showOrderHeader && Object.keys(payload).filter(k => k !== 'Lines').length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-700 mb-1">{title}</div>
              <div className="border-[0.5px] rounded-md overflow-hidden bg-white">
                <Table>
                  <TableBody>
                    {Object.entries(payload)
                      .filter(([key]) => key !== 'Lines' && key !== 'CustomerID' && key !== 'Type')
                      .map(([key, value]) => {
                        const isPlaceholder = typeof value === 'string' && (value.includes('<REQUIRED:') || value.includes('<SALE_ID_PLACEHOLDER>'));
                        const isEmpty = value === null || value === undefined || value === '';
                        const isMissing = isPlaceholder || isEmpty;
                        
                        // Special handling for Customer field
                        const isCustomerField = key === 'Customer' || key === 'customer_name';
                        // Only show "not found" if matchingDetails says not found AND customer wasn't actually found (no sale_id/CustomerID)
                        const customerNotMatched = isCustomerField && matchingDetails?.customer && !matchingDetails.customer.found && !customerWasFound;
                        // Check if customer was matched - get ID from payload first, then matching details
                        const customerId = (payload.CustomerID && String(payload.CustomerID)) || (matchingDetails?.customer?.cin7_id && String(matchingDetails.customer.cin7_id)) || null;
                        const customerMatched = isCustomerField && customerWasFound && customerId;
                        
                        return (
                          <TableRow key={key} className={`bg-white ${isMissing ? 'bg-orange-50' : ''}`}>
                            <TableCell className="font-medium text-xs text-gray-700 bg-white">{key}</TableCell>
                            <TableCell className={`text-xs bg-white ${customerNotMatched ? 'text-red-600' : isPlaceholder ? 'text-orange-600 font-medium italic' : isEmpty ? 'text-orange-600 italic' : 'text-gray-900'}`}>
                              <div className="flex items-center gap-1.5">
                                <span>{isPlaceholder ? value : (isEmpty ? <span className="italic">(missing)</span> : String(value))}</span>
                                {customerMatched && (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span className="inline-flex items-center justify-center rounded-full border border-transparent bg-green-500 hover:bg-green-600 cursor-help h-4 w-4">
                                        <Check className="h-2.5 w-2.5 text-white stroke-[3]" />
                                      </span>
                                    </TooltipTrigger>
                                    <TooltipContent className="bg-black text-white">
                                      <p className="text-xs">ID: {String(customerId || 'N/A')}</p>
                                    </TooltipContent>
                                  </Tooltip>
                                )}
                                {customerNotMatched && (
                                  <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-destructive font-sans">Not found in Cin7</Badge>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}
          
          {/* Line Items */}
          <div>
            <div className="text-xs font-semibold text-gray-700 mb-1">{title}</div>
            {(payload.Lines.length > 0 || (orderContext?.removed_products && orderContext.removed_products.length > 0) || (matchingDetails?.products && matchingDetails.products.some(p => !p.found))) ? (
              <div className="border-[1px] rounded-md overflow-hidden bg-white">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-gray-50">
                        <TableHead className="font-semibold text-xs">SKU</TableHead>
                        <TableHead className="font-semibold text-xs text-right">Quantity</TableHead>
                        <TableHead className="font-semibold text-xs text-right">Price</TableHead>
                        <TableHead className="font-semibold text-xs text-right">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {/* Show matched products (from payload.Lines) */}
                      {payload.Lines.map((line, idx) => {
                        const hasPlaceholder = line.ProductID && String(line.ProductID).includes('<REQUIRED:');
                        const missingProductId = !line.ProductID || hasPlaceholder;
                        const hasMissingFields = missingProductId || !line.SKU;
                        
                        // Find matching product details
                        const productMatch = matchingDetails?.products?.find(p => p.sku === line.SKU);
                        const isMatched = productMatch?.found && line.ProductID && !hasPlaceholder;
                        const isUnmatched = productMatch && !productMatch.found; // Product was checked but not found
                        const productId = (line.ProductID && String(line.ProductID)) || (productMatch?.cin7_id && String(productMatch.cin7_id)) || null;
                        
                        // Get CSV values as fallback for quantity and price
                        const csvValues = getCsvValuesForLine(line.SKU);
                        
                        // Check if payload quantity is valid (not undefined, null, or NaN)
                        // Note: 0 is a valid quantity, so we only check for undefined, null, or NaN
                        const payloadQuantityValid = line.Quantity !== undefined && line.Quantity !== null && 
                          !isNaN(Number(line.Quantity));
                        const quantity = payloadQuantityValid 
                          ? line.Quantity 
                          : (() => {
                              const csvQty = parseNumericValue(csvValues?.quantity);
                              return csvQty !== null ? csvQty : '-';
                            })();
                        
                        // Check if payload price is valid (not undefined, null, or NaN)
                        // Note: 0 is a valid price, so we only check for undefined, null, or NaN
                        const payloadPriceValid = line.Price !== undefined && line.Price !== null && 
                          !isNaN(Number(line.Price));
                        const price = payloadPriceValid 
                          ? line.Price 
                          : (() => {
                              const csvPrice = parseNumericValue(csvValues?.price);
                              return csvPrice !== null ? csvPrice : '-';
                            })();
                        
                        const total = (quantity !== '-' && price !== '-') 
                          ? formatCurrency(Number(quantity) * Number(price))
                          : '-';
                        
                        // Remove red row highlighting - use white background for all rows
                        const rowClassName = hasMissingFields && !isMatched ? 'bg-orange-50' : 'bg-white';
                        const textClassName = isUnmatched ? 'text-gray-900' : (!line.SKU ? 'text-orange-600 italic' : 'text-gray-900');
                        
                        return (
                          <TableRow key={idx} className={rowClassName}>
                            <TableCell className={`text-xs ${textClassName}`}>
                              <div className="flex items-center gap-1.5">
                                <span>{line.SKU || <span className="italic">(missing)</span>}</span>
                                {isMatched && productId && (
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span className="inline-flex items-center justify-center rounded-full border border-transparent bg-green-500 hover:bg-green-600 cursor-help h-4 w-4">
                                        <Check className="h-2.5 w-2.5 text-white stroke-[3]" />
                                      </span>
                                    </TooltipTrigger>
                                    <TooltipContent className="bg-black text-white">
                                      <p className="text-xs">ID: {String(productId || 'N/A')}</p>
                                    </TooltipContent>
                                  </Tooltip>
                                )}
                                {isUnmatched && (
                                  <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-destructive font-sans">
                                    SKU Missing in Cin7
                                  </Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="text-right text-xs text-gray-900">{quantity !== '-' ? String(quantity) : '-'}</TableCell>
                            <TableCell className="text-right text-xs text-gray-900">{price !== '-' ? `$${Number(price).toFixed(2)}` : '-'}</TableCell>
                            <TableCell className="text-right text-xs text-gray-900">{total}</TableCell>
                          </TableRow>
                        );
                      })}
                      
                      {/* Show unmatched products from removed_products */}
                      {orderContext?.removed_products && orderContext.removed_products.map((removed, idx) => {
                        const rowData = removed.row_data || {};
                        const sku = removed.sku;
                        const quantity = rowData.Quantity || rowData.quantity || rowData.qty || '-';
                        const price = rowData.Price || rowData.price || rowData.unit_price || '-';
                        const total = (quantity !== '-' && price !== '-') 
                          ? formatCurrency(Number(quantity) * Number(price))
                          : '-';
                        
                        return (
                          <TableRow key={`removed-${idx}`} className="bg-white">
                            <TableCell className="text-xs text-gray-900">
                              <div className="flex items-center gap-1.5">
                                <span>{sku}</span>
                                <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-destructive font-sans">
                                  No match found - not created in Cin7
                                </Badge>
                              </div>
                            </TableCell>
                            <TableCell className="text-right text-xs text-gray-900">{quantity}</TableCell>
                            <TableCell className="text-right text-xs text-gray-900">{price !== '-' ? `$${Number(price).toFixed(2)}` : '-'}</TableCell>
                            <TableCell className="text-right text-xs text-gray-900">{total}</TableCell>
                          </TableRow>
                        );
                      })}
                      
                      {/* Show unmatched products from matching_details that aren't in payload.Lines or removed_products */}
                      {matchingDetails?.products && matchingDetails.products
                        .filter(p => !p.found && !payload.Lines.some(line => line.SKU === p.sku))
                        .filter(p => !orderContext?.removed_products?.some(removed => removed.sku === p.sku))
                        .map((unmatched, idx) => {
                          // Try to get quantity and price from orderContext.all_rows using improved lookup
                          const csvValues = getCsvValuesForLine(unmatched.sku);
                          const quantity = (() => {
                            const csvQty = parseNumericValue(csvValues?.quantity);
                            return csvQty !== null ? csvQty : '-';
                          })();
                          const price = (() => {
                            const csvPrice = parseNumericValue(csvValues?.price);
                            return csvPrice !== null ? csvPrice : '-';
                          })();
                          const total = (quantity !== '-' && price !== '-') 
                            ? formatCurrency(Number(quantity) * Number(price))
                            : '-';
                          
                          return (
                            <TableRow key={`unmatched-${idx}`} className="bg-white">
                              <TableCell className="text-xs text-gray-900">
                                <div className="flex items-center gap-1.5">
                                  <span>{unmatched.sku}</span>
                                  <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-destructive font-sans">
                                    SKU Missing in Cin7
                                  </Badge>
                                </div>
                              </TableCell>
                              <TableCell className="text-right text-xs text-gray-900">{quantity !== '-' ? String(quantity) : '-'}</TableCell>
                              <TableCell className="text-right text-xs text-gray-900">{price !== '-' ? `$${Number(price).toFixed(2)}` : '-'}</TableCell>
                              <TableCell className="text-right text-xs text-gray-900">{total}</TableCell>
                            </TableRow>
                          );
                        })}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ) : (
              <div className="p-2 bg-gray-50 rounded border border-gray-200 text-xs text-gray-500 text-center">
                No line items in this payload
              </div>
            )}
          </div>
          </div>
        </TooltipProvider>
      );
    } else {
      // Regular payload (sale_payload - order header only)
      return (
        <TooltipProvider>
          <div>
          <div className="text-xs font-semibold text-gray-700 mb-1">{title}</div>
          <div className="border-[0.5px] rounded-md overflow-hidden bg-white">
            <Table>
              <TableBody>
                {Object.entries(payload)
                  .filter(([key]) => key !== 'CustomerID' && key !== 'Type')
                  .map(([key, value]) => {
                  const isPlaceholder = typeof value === 'string' && (value.includes('<REQUIRED:') || value.includes('<SALE_ID_PLACEHOLDER>'));
                  const isEmpty = value === null || value === undefined || value === '';
                  const isMissing = isPlaceholder || isEmpty;
                  
                  // Special handling for Customer field
                  const isCustomerField = key === 'Customer' || key === 'customer_name';
                  // Only show "not found" if matchingDetails says not found AND customer wasn't actually found (no sale_id/CustomerID)
                  const customerNotMatched = isCustomerField && matchingDetails?.customer && !matchingDetails.customer.found && !customerWasFound;
                  // Check if customer was matched - get ID from payload first, then matching details
                  const customerId = (payload.CustomerID && String(payload.CustomerID)) || (matchingDetails?.customer?.cin7_id && String(matchingDetails.customer.cin7_id)) || null;
                  const customerMatched = isCustomerField && customerWasFound && customerId;
                  
                  return (
                    <TableRow key={key} className={`bg-white ${isMissing ? 'bg-orange-50' : ''}`}>
                      <TableCell className="font-medium text-xs text-gray-700 bg-white">{key}</TableCell>
                      <TableCell className={`text-xs bg-white ${customerNotMatched ? 'text-red-600' : isPlaceholder ? 'text-orange-600 font-medium italic' : isEmpty ? 'text-orange-600 italic' : 'text-gray-900'}`}>
                        <div className="flex items-center gap-1.5">
                          <span>{isPlaceholder ? (
                            <span className="italic">{value}</span>
                          ) : (
                            <span>{isEmpty ? <span className="italic">(missing)</span> : String(value)}</span>
                          )}</span>
                          {customerMatched && (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="inline-flex items-center justify-center rounded-full border border-transparent bg-green-500 hover:bg-green-600 cursor-help h-4 w-4">
                                  <Check className="h-2.5 w-2.5 text-white stroke-[3]" />
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="text-xs">ID: {customerId}</p>
                              </TooltipContent>
                            </Tooltip>
                          )}
                          {customerNotMatched && (
                            <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-destructive font-sans">Not found in Cin7</Badge>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
        </TooltipProvider>
      );
    }
  };

  return (
    <div className="h-full w-full overflow-y-auto">
      <div className="p-6 space-y-6">
        <Tabs 
          value={activeTab} 
          onValueChange={(value) => {
            setActiveTab(value);
            // Update URL based on tab
            const params = new URLSearchParams(location.search);
            if (value === 'failed') {
              params.set('tab', 'failed');
              params.delete('review');
            } else if (value === 'completed') {
              params.set('tab', 'completed');
              // Keep review param if it exists
            } else if (value === 'uploads') {
              params.set('tab', 'uploads');
              params.delete('review');
            }
            navigate(`/?${params.toString()}`, { replace: true });
          }} 
          defaultValue="completed" 
          className="w-full"
        >
          <div className="space-y-3 mb-4">
            <div className="flex items-center justify-between">
              <TabsList className="h-9 p-1">
                <TabsTrigger value="completed" className="text-xs py-1.5 px-3">
                  Sync'd Orders
                </TabsTrigger>
                <TabsTrigger value="failed" className="text-xs py-1.5 px-3">
                  Failed Orders
                </TabsTrigger>
                <TabsTrigger value="uploads" className="text-xs py-1.5 px-3">All Uploads</TabsTrigger>
              </TabsList>
              <div className="flex items-center gap-2">
                {/* File Upload */}
                <div
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onClick={() => !isUploading && selectedClientId && fileInputRef.current?.click()}
                  className={cn(
                    "relative border-2 border-dashed rounded-md px-4 py-1.5 cursor-pointer transition-colors",
                    "bg-transparent border-muted-foreground/30 hover:border-primary/50 hover:bg-primary/5",
                    (isUploading || !selectedClientId) && "opacity-50 cursor-not-allowed",
                    "min-w-[160px] flex items-center justify-center gap-2"
                  )}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    onChange={handleFileSelect}
                    className="hidden"
                    disabled={isUploading}
                  />
                  {isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-xs">Uploading...</span>
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4" />
                      <span className="text-xs">Upload CSV</span>
                    </>
                  )}
                </div>
                <Button onClick={handleRefresh} variant="ghost" disabled={isRefreshing} className="h-8 px-3 text-xs">
                  <RefreshCw className={cn("h-4 w-4 mr-2", isRefreshing && "animate-spin")} />
                  Refresh
                </Button>
                {/* Bulk Actions */}
                <div className="flex items-center gap-2" style={{ minHeight: '36px' }}>
                {selectedOrderIds.size > 0 && (
                  <>
                    <Button onClick={bulkRetryOrders} variant="default" size="sm" className="h-7 text-xs px-2">
                      <RotateCcw className="h-3 w-3 mr-1.5" />
                      Retry ({selectedOrderIds.size})
                    </Button>
                    <Button onClick={bulkResolveOrders} variant="outline" size="sm" className="h-7 text-xs px-2">
                      Review ({selectedOrderIds.size})
                    </Button>
                  </>
                )}
                </div>
              </div>
            </div>
            {/* Global Filters and Search */}
            <div className="flex items-center gap-3">
              {activeTab === 'completed' && (
                <Tabs 
                  value={reviewFilterTab} 
                  onValueChange={(value) => {
                    setReviewFilterTab(value);
                    // Update URL
                    const params = new URLSearchParams(location.search);
                    params.set('tab', 'completed');
                    if (value === 'needs-review') {
                      params.set('review', 'needs-review');
                    } else {
                      params.delete('review');
                    }
                    navigate(`/?${params.toString()}`, { replace: true });
                  }} 
                  className="w-auto"
                >
                  <TabsList className="h-9 p-1">
                    <TabsTrigger 
                      value="needs-review" 
                      className="text-xs py-1.5 px-3"
                      disabled={unreviewedCount === 0}
                    >
                      Needs Review
                      {unreviewedCount > 0 && (
                        <Badge variant="default" className="ml-1.5 text-[10px] px-1.5 py-0 h-4 w-6 flex items-center justify-center bg-blue-500 shadow-none hover:bg-blue-500">{unreviewedCount}</Badge>
                      )}
                    </TabsTrigger>
                    <TabsTrigger value="all" className="text-xs py-1.5 px-3">
                      All
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              )}
              {activeTab === 'failed' && (
                <Tabs 
                  value={failedFilterTab} 
                  onValueChange={(value) => {
                    setFailedFilterTab(value);
                    // Update URL
                    const params = new URLSearchParams(location.search);
                    params.set('tab', 'failed');
                    if (value === 'all') {
                      params.set('review', 'all');
                    } else {
                      params.delete('review');
                    }
                    navigate(`/?${params.toString()}`, { replace: true });
                  }} 
                  className="w-auto"
                >
                  <TabsList className="h-9 p-1">
                    <TabsTrigger 
                      value="needs-review" 
                      className="text-xs py-1.5 px-3"
                      disabled={unreviewedFailedCount === 0}
                    >
                      Needs Review
                      {unreviewedFailedCount > 0 && (
                        <Badge variant="default" className="ml-1.5 text-[10px] px-1.5 py-0 h-4 w-6 flex items-center justify-center bg-red-500 shadow-none hover:bg-red-500">{unreviewedFailedCount}</Badge>
                      )}
                    </TabsTrigger>
                    <TabsTrigger value="all" className="text-xs py-1.5 px-3">
                      All
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              )}
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-9 text-xs"
                />
              </div>
            </div>
          </div>

          <TabsContent value="uploads">
            {/* Uploads Table */}
            <div className="overflow-x-auto">
          {loading && isInitialLoad ? (
            <div className="text-center py-8 text-muted-foreground">Loading...</div>
          ) : filteredAndSortedUploads.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">No uploads found</div>
          ) : (
            <div className="border-[1px] rounded-md overflow-hidden bg-white">
              <Table className="border-0">
              <TableHeader>
                <TableRow>
                  <TableHead>Filename</TableHead>
                  <TableHead>
                    <button
                      onClick={() => {
                        if (dateSortDirection === null) {
                          setDateSortDirection('desc');
                        } else if (dateSortDirection === 'desc') {
                          setDateSortDirection('asc');
                        } else {
                          setDateSortDirection(null);
                        }
                      }}
                      className="flex items-center gap-1 hover:opacity-70 transition-opacity text-left"
                    >
                      Date
                      {dateSortDirection === 'asc' && <ArrowUp className="h-3 w-3" />}
                      {dateSortDirection === 'desc' && <ArrowDown className="h-3 w-3" />}
                    </button>
                  </TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Orders</TableHead>
                  <TableHead className="text-right">Successful</TableHead>
                  <TableHead className="text-right">Failed</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAndSortedUploads.map((upload) => {
                  const isExpanded = expandedUploads.has(upload.id);
                  // Count partial_success as failed, not successful
                  const successfulOrders = upload.order_results?.filter(or => 
                    or.status === 'success' && or.error_type !== 'partial_success'
                  ) || [];
                  const failedOrdersForUpload = upload.order_results?.filter(or => 
                    or.status === 'failed' || or.error_type === 'partial_success'
                  ) || [];
                  
                  return (
                    <React.Fragment key={upload.id}>
                      <TableRow 
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => {
                          const newExpanded = new Set(expandedUploads);
                          if (newExpanded.has(upload.id)) {
                            newExpanded.delete(upload.id);
                          } else {
                            newExpanded.add(upload.id);
                          }
                          setExpandedUploads(newExpanded);
                        }}
                      >
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">{upload.filename}</span>
                            {upload.has_csv && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  viewCsv(upload.id);
                                }}
                                className="h-6 px-2"
                              >
                                <Eye className="h-3 w-3" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{formatDate(upload.created_at)}</TableCell>
                        <TableCell>
                          {(() => {
                            // Show "Processing" only if status is processing, otherwise show "Processed"
                            const displayStatus = upload.status === 'processing' ? 'processing' : 'processed';
                            return getStatusBadge(displayStatus);
                          })()}
                        </TableCell>
                        <TableCell className="text-right">{upload.order_results?.length || 0}</TableCell>
                        <TableCell className="text-right text-green-600">{successfulOrders.length}</TableCell>
                        <TableCell className="text-right text-red-600">{failedOrdersForUpload.length}</TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                const newExpanded = new Set(expandedUploads);
                                if (newExpanded.has(upload.id)) {
                                  newExpanded.delete(upload.id);
                                } else {
                                  newExpanded.add(upload.id);
                                }
                                setExpandedUploads(newExpanded);
                              }}
                              className="h-7 text-xs px-0"
                            >
                              {isExpanded ? 'Hide Details' : 'See Details'}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {isExpanded && (
                        <TableRow>
                          <TableCell colSpan={7} className="bg-muted/30">
                            <div className="p-3 space-y-3">
                              {/* Duplicate Message */}
                              {upload.status === 'duplicate' && upload.error_log && upload.error_log.length > 0 && (
                                <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-3">
                                  <div className="flex items-start gap-2">
                                    <AlertCircle className="h-4 w-4 text-yellow-600 mt-0.5" />
                                    <div className="flex-1">
                                      <div className="font-semibold text-sm text-yellow-800 mb-1">Duplicate Upload Detected</div>
                                      {upload.error_log[0] && typeof upload.error_log[0] === 'object' && (
                                        <div className="text-xs text-yellow-700 space-y-1">
                                          <div>{upload.error_log[0].message || 'This file was already processed recently'}</div>
                                          {upload.error_log[0].duplicate_of_upload_id && (
                                            <div>
                                              Original upload ID: <span className="font-mono">{upload.error_log[0].duplicate_of_upload_id}</span>
                                            </div>
                                          )}
                                          {upload.error_log[0].duplicate_of_created_at && (
                                            <div>
                                              Original upload time: {formatDate(upload.error_log[0].duplicate_of_created_at)}
                                            </div>
                                          )}
                                          {upload.error_log[0].duplicate_of_status && (
                                            <div>
                                              Original status: <Badge variant="secondary" className="ml-1">{upload.error_log[0].duplicate_of_status}</Badge>
                                            </div>
                                          )}
                                        </div>
                                      )}
                                      {typeof upload.error_log[0] === 'string' && (
                                        <div className="text-xs text-yellow-700">{upload.error_log[0]}</div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              )}
                              {/* Failed Orders */}
                              {failedOrdersForUpload.length > 0 && (
                                <div>
                                  <h4 className="font-semibold text-xs mb-1.5 flex items-center gap-2 text-red-600">
                                    <XCircle className="h-3.5 w-3.5" />
                                    Failed Orders ({failedOrdersForUpload.length})
                                  </h4>
                                  <div className="space-y-2">
                                    {failedOrdersForUpload.map((order) => (
                                      <div key={order.id} className="bg-red-50 border border-red-200 rounded p-3">
                                        <div className="space-y-3">
                                          {/* Order Header with Actions */}
                                          <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                              <div className="text-xs font-semibold text-gray-700">Order: {order.order_key}</div>
                                              {order.error_type && getErrorTypeBadge(order.error_type)}
                                            </div>
                                            <div className="flex items-center gap-1">
                                              {(order.sale_payload || order.sale_order_payload || order.what_is_needed) && (
                                                <Button
                                                  variant="ghost"
                                                  size="sm"
                                                  onClick={(e) => {
                                                    e.stopPropagation();
                                                    setViewingOrderPayload(order);
                                                    setJsonModalOpen(true);
                                                  }}
                                                  className="h-7 w-7 p-0"
                                                  title="View JSON payloads (dev)"
                                                >
                                                  <Code className="h-3 w-3 text-muted-foreground" />
                                                </Button>
                                              )}
                                              <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  retryOrder(order.id);
                                                }}
                                                className="h-7 text-xs px-2"
                                              >
                                                <RotateCcw className="h-3 w-3 mr-1" />
                                                Retry
                                              </Button>
                                            </div>
                                          </div>
                                          
                                    {/* Error Message */}
                                    {order.error_message && (
                                      <div>
                                        <div className="font-semibold text-xs">
                                          Error Message: <span className="text-red-600 font-normal">{order.error_message}</span>
                                        </div>
                                      </div>
                                    )}
                                          
                                          {/* Order Details */}
                                          {(order.sale_payload || order.sale_order_payload) && (
                                            <div className="space-y-2 max-h-[400px] overflow-y-auto">
                                              {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details, order)}
                                              {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details, order)}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {/* Successful Orders */}
                              {successfulOrders.length > 0 && (
                                <div>
                                  <h4 className="font-semibold text-xs mb-1.5 flex items-center gap-2 text-green-600">
                                    <CheckCircle2 className="h-3.5 w-3.5" />
                                    Successful Orders ({successfulOrders.length})
                                  </h4>
                                  <div className="space-y-2">
                                    {successfulOrders.map((order) => (
                                      <div key={order.id} className="bg-green-50 border border-green-200 rounded p-3">
                                        <div className="space-y-3">
                                          {/* Order Header with Actions */}
                                          <div className="flex items-center justify-between">
                                            <div className="text-xs font-semibold text-gray-700">Order: {order.order_key}</div>
                                            {(order.sale_payload || order.sale_order_payload || order.what_is_needed) && (
                                              <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={(e) => {
                                                  e.stopPropagation();
                                                  setViewingOrderPayload(order);
                                                  setJsonModalOpen(true);
                                                }}
                                                className="h-7 w-7 p-0"
                                                title="View JSON payloads (dev)"
                                              >
                                                <Code className="h-3 w-3 text-muted-foreground" />
                                              </Button>
                                            )}
                                          </div>
                                          {/* Order Details for successful orders */}
                                          {(order.sale_payload || order.sale_order_payload) && (
                                            <div className="space-y-2 max-h-[400px] overflow-y-auto">
                                              {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details, order)}
                                              {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details, order)}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {successfulOrders.length === 0 && failedOrdersForUpload.length === 0 && (
                                <div className="text-center py-4 text-muted-foreground text-xs">
                                  No order results yet
                                </div>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  );
                })}
              </TableBody>
              </Table>
            </div>
          )}
        </div>
          </TabsContent>

          <TabsContent value="failed">
            {/* Failed Orders View */}
            <div className="space-y-4">
              {/* Failed Orders Table */}
              <div className="overflow-x-auto">
                {failedOrdersLoading && isFailedOrdersInitialLoad ? (
                  <div className="text-center py-8 text-muted-foreground">Loading...</div>
                ) : filteredAndSortedFailedOrders.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">No failed orders found</div>
                ) : (
                  <div className="border-[1px] rounded-md overflow-hidden bg-white">
                    <Table className="border-0">
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-10">
                          <Checkbox
                            checked={selectedOrderIds.size === filteredAndSortedFailedOrders.length && filteredAndSortedFailedOrders.length > 0 && filteredAndSortedFailedOrders.every(o => selectedOrderIds.has(o.id))}
                            onCheckedChange={(checked) => {
                              if (checked) {
                                setSelectedOrderIds(new Set(filteredAndSortedFailedOrders.map(o => o.id)));
                              } else {
                                setSelectedOrderIds(new Set());
                              }
                            }}
                          />
                        </TableHead>
                        <TableHead className="w-10"></TableHead>
                        <TableHead className="text-xs font-semibold text-center">Reviewed</TableHead>
                        <TableHead className="text-xs font-semibold">Order</TableHead>
                        <TableHead className="text-xs font-semibold">Customer</TableHead>
                        <TableHead className="text-xs font-semibold">PO #</TableHead>
                        <TableHead className="text-xs font-semibold">Notes</TableHead>
                        <TableHead className="text-xs font-semibold">Error Type</TableHead>
                        <TableHead className="text-xs font-semibold">Retry Count</TableHead>
                        <TableHead className="text-xs font-semibold">Last Retry</TableHead>
                        <TableHead className="text-xs font-semibold">Source Upload</TableHead>
                        <TableHead className="text-xs font-semibold">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredAndSortedFailedOrders.map((order) => {
                        const isExpanded = expandedFailedOrders.has(order.id);
                        const isSelected = selectedOrderIds.has(order.id);
                        
                        return (
                          <React.Fragment key={order.id}>
                            <TableRow 
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() => toggleExpandFailedOrder(order.id)}
                            >
                              <TableCell className="text-xs" onClick={(e) => { e.stopPropagation(); }}>
                                <Checkbox
                                  checked={isSelected}
                                  onCheckedChange={(checked) => toggleSelectOrder(order.id, checked)}
                                />
                              </TableCell>
                              <TableCell className="text-xs">
                                {isExpanded ? (
                                  <ChevronDown className="h-3.5 w-3.5" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5" />
                                )}
                              </TableCell>
                              <TableCell onClick={(e) => e.stopPropagation()} className="cursor-default text-center">
                                <button
                                  onClick={() => markFailedOrderAsReviewed(order.id, !order.resolved_at)}
                                  className="hover:opacity-80 transition-opacity inline-flex items-center justify-center"
                                  title={order.resolved_at ? "Mark as unreviewed" : "Mark as reviewed"}
                                >
                                  {order.resolved_at ? (
                                    <div className="h-4 w-4 rounded-full bg-green-500 flex items-center justify-center">
                                      <Check className="h-2.5 w-2.5 text-white stroke-[3]" />
                                    </div>
                                  ) : (
                                    <Circle className="h-4 w-4 text-gray-400" />
                                  )}
                                </button>
                              </TableCell>
                              <TableCell className="text-xs">
                                <span className="font-medium">{order.order_key}</span>
                              </TableCell>
                              <TableCell className="text-xs whitespace-nowrap">
                                {order.customer_name || '-'}
                              </TableCell>
                              <TableCell className="text-xs">
                                {order.po_number || '-'}
                              </TableCell>
                              <TableCell className="text-xs max-w-xs">
                                {order.review_notes ? (
                                  <TooltipProvider>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <span className="text-xs text-gray-600 truncate block">
                                          {order.review_notes}
                                        </span>
                                      </TooltipTrigger>
                                      <TooltipContent className="max-w-md">
                                        <p>{order.review_notes}</p>
                                      </TooltipContent>
                                    </Tooltip>
                                  </TooltipProvider>
                                ) : (
                                  <span className="text-xs text-gray-400">-</span>
                                )}
                              </TableCell>
                              <TableCell className="text-xs whitespace-nowrap">
                                {getErrorTypeBadge(order.error_type)}
                              </TableCell>
                              <TableCell className="text-xs">
                                {order.retry_count || 0}
                              </TableCell>
                              <TableCell className="text-xs">
                                {order.last_retry_at ? formatDate(order.last_retry_at) : '-'}
                              </TableCell>
                              <TableCell className="text-xs whitespace-nowrap">
                                {order.upload ? (
                                  <div>
                                    <div className="font-medium">{order.upload.filename}</div>
                                    <div className="text-muted-foreground text-[10px]">{formatDate(order.upload.created_at)}</div>
                                  </div>
                                ) : '-'}
                              </TableCell>
                              <TableCell className="text-xs" onClick={(e) => e.stopPropagation()}>
                                <div className="flex items-center gap-1">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-6 px-2 text-xs"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      retryOrder(order.id);
                                    }}
                                  >
                                    <RotateCcw className="h-3 w-3 mr-1" />
                                    Retry
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                            {isExpanded && (
                              <TableRow>
                                <TableCell colSpan={12} className="bg-muted/30">
                                  <div className="p-3 space-y-3">
                                    {/* Order Header with Actions */}
                                    <div className="flex items-center justify-between mb-2">
                                      <div className="text-xs font-semibold text-gray-700">Order: {order.order_key}</div>
                                      <div className="flex items-center gap-1">
                                        {(order.sale_payload || order.sale_order_payload || order.what_is_needed) && (
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setViewingOrderPayload(order);
                                              setJsonModalOpen(true);
                                            }}
                                            className="h-7 w-7 p-0"
                                            title="View JSON payloads (dev)"
                                          >
                                            <Code className="h-3 w-3 text-muted-foreground" />
                                          </Button>
                                        )}
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            retryOrder(order.id);
                                          }}
                                          className="h-7 text-xs px-2"
                                        >
                                          <RotateCcw className="h-3 w-3 mr-1" />
                                          Retry
                                        </Button>
                                      </div>
                                    </div>

                                    {/* Error Message */}
                                    {order.error_message && (
                                      <div>
                                        <div className="font-semibold text-xs">
                                          Error Message: <span className="text-red-600 font-normal">{order.error_message}</span>
                                        </div>
                                      </div>
                                    )}

                                    {/* Order Details - reuse existing renderPayloadTable */}
                                    {(order.sale_payload || order.sale_order_payload) && (
                                      <div className="space-y-2 max-h-[400px] overflow-y-auto">
                                        {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details, order)}
                                        {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details, order)}
                                      </div>
                                    )}
                                  </div>
                                </TableCell>
                              </TableRow>
                            )}
                          </React.Fragment>
                        );
                      })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="completed">
            {/* Sync'd Orders View */}
            <div className="space-y-4">
              {/* Sync'd Orders Table */}
              <div className="overflow-x-auto">
                {completedOrdersLoading && isCompletedOrdersInitialLoad ? (
                  <div className="text-center py-8 text-muted-foreground">Loading...</div>
                ) : filteredAndSortedCompletedOrders.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">No sync'd orders found</div>
                ) : (
                  <div className="border-[1px] rounded-md overflow-hidden bg-white">
                    <Table className="border-0">
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-12 text-center">Reviewed</TableHead>
                          <TableHead>Order</TableHead>
                          <TableHead>Customer</TableHead>
                          <TableHead>PO #</TableHead>
                          <TableHead>
                            <button
                              onClick={() => {
                                if (dateSortDirection === null) {
                                  setDateSortDirection('desc');
                                } else if (dateSortDirection === 'desc') {
                                  setDateSortDirection('asc');
                                } else {
                                  setDateSortDirection(null);
                                }
                              }}
                              className="flex items-center gap-1 hover:opacity-70 transition-opacity text-left"
                            >
                              Completed At
                              {dateSortDirection === 'asc' && <ArrowUp className="h-3 w-3" />}
                              {dateSortDirection === 'desc' && <ArrowDown className="h-3 w-3" />}
                            </button>
                          </TableHead>
                          <TableHead>Open in Cin7</TableHead>
                          <TableHead>Source Upload</TableHead>
                          <TableHead>Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                      {filteredAndSortedCompletedOrders.map((order) => {
                        const isExpanded = expandedCompletedOrders.has(order.id);
                        // Extract customer and PO from sale_payload if not in order data
                        const customerName = order.customer_name || 
                          (order.sale_payload && (order.sale_payload.Customer || order.sale_payload.customer_name)) || 
                          '-';
                        const poNumber = order.po_number || 
                          (order.sale_payload && (order.sale_payload.CustomerReference || order.sale_payload.customer_reference)) || 
                          '-';
                        
                        return (
                          <React.Fragment key={order.id}>
                            <TableRow 
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}
                            >
                              <TableCell onClick={(e) => e.stopPropagation()} className="cursor-default text-center">
                                <button
                                  onClick={() => markOrderAsReviewed(order.id, !order.reviewed)}
                                  className="hover:opacity-80 transition-opacity inline-flex items-center justify-center"
                                  title={order.reviewed ? "Mark as unreviewed" : "Mark as reviewed"}
                                >
                                  {order.reviewed ? (
                                    <div className="h-4 w-4 rounded-full bg-green-500 flex items-center justify-center">
                                      <Check className="h-2.5 w-2.5 text-white stroke-[3]" />
                                    </div>
                                  ) : (
                                    <Circle className="h-4 w-4 text-gray-400" />
                                  )}
                                </button>
                              </TableCell>
                              <TableCell>
                                <span className="font-medium">{order.order_key}</span>
                              </TableCell>
                              <TableCell className="whitespace-nowrap">
                                {customerName}
                              </TableCell>
                              <TableCell>
                                {poNumber}
                              </TableCell>
                              <TableCell>
                                {formatDate(order.processed_at)}
                              </TableCell>
                              <TableCell onClick={(e) => e.stopPropagation()}>
                                {order.sale_id ? (
                                  <a
                                    href={`https://inventory.dearsystems.com/Sale#${order.sale_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-600 hover:text-blue-800 hover:underline font-medium"
                                  >
                                    Open in Cin7
                                  </a>
                                ) : '-'}
                              </TableCell>
                              <TableCell className="whitespace-nowrap">
                                {order.upload ? (
                                  <div className="text-xs">
                                    <div className="font-medium">{order.upload.filename}</div>
                                    <div className="text-muted-foreground">{formatDate(order.upload.created_at)}</div>
                                  </div>
                                ) : '-'}
                              </TableCell>
                              <TableCell onClick={(e) => e.stopPropagation()}>
                                <div className="flex items-center gap-2">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      const newExpanded = new Set(expandedCompletedOrders);
                                      if (newExpanded.has(order.id)) {
                                        newExpanded.delete(order.id);
                                      } else {
                                        newExpanded.add(order.id);
                                      }
                                      setExpandedCompletedOrders(newExpanded);
                                    }}
                                    className="h-7 text-xs px-0"
                                  >
                                    {isExpanded ? 'Hide Details' : 'See Details'}
                                  </Button>
                                  {(order.sale_payload || order.sale_order_payload || order.what_is_needed || order.order_data) && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setViewingOrderPayload(order);
                                        setJsonModalOpen(true);
                                      }}
                                      className="h-7 w-7 p-0"
                                      title="View JSON payloads (dev)"
                                    >
                                      <Code className="h-3 w-3 text-muted-foreground" />
                                    </Button>
                                  )}
                                </div>
                              </TableCell>
                            </TableRow>
                            {isExpanded && (
                              <TableRow>
                                <TableCell colSpan={8} className="bg-muted/30">
                                  <div className="p-4 space-y-4">

                                    {/* Order Details - reuse existing renderPayloadTable */}
                                    {(order.sale_payload || order.sale_order_payload) && (
                                      <div className="space-y-3 max-h-[500px] overflow-y-auto">
                                        {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details, order)}
                                        {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details, order)}
                                      </div>
                                    )}

                                  </div>
                                </TableCell>
                              </TableRow>
                            )}
                          </React.Fragment>
                        );
                      })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
      
      {/* JSON Payload Modal */}
      <Dialog open={jsonModalOpen} onOpenChange={setJsonModalOpen}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Code className="h-5 w-5" />
              {viewingOrderPayload?.order_results && Array.isArray(viewingOrderPayload.order_results) ? 'Upload API Logs' : 'Order Payload Details'}
            </DialogTitle>
            <DialogDescription>
              {viewingOrderPayload?.order_results && Array.isArray(viewingOrderPayload.order_results)
                ? `API logs for upload: ${viewingOrderPayload.upload?.filename || 'N/A'}`
                : viewingOrderPayload?.order_data?.attempted_send === false 
                  ? "Prepared payloads (not sent to Cin7)" 
                  : "Payloads sent to Cin7"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto space-y-6">
            {/* Error Message */}
            {viewingOrderPayload?.error_message && (
              <div className="p-3 bg-red-50 rounded border border-red-200">
                <div className="text-sm font-semibold text-red-800 mb-2">Error Message:</div>
                <div className="text-sm text-red-700 break-words">{viewingOrderPayload.error_message}</div>
              </div>
            )}
            
            
            {/* Helper function to render payload as JSON */}
            {(() => {
              const renderPayloadJson = (payload, title) => {
                if (!payload) return null;
                
                // If payload is a string (raw JSON), format it while preserving order
                if (typeof payload === 'string') {
                  try {
                    // Parse and stringify to format, but JavaScript preserves object key order (ES2015+)
                    const parsed = JSON.parse(payload);
                    const formatted = JSON.stringify(parsed, null, 2);
                    return (
                      <div className="space-y-2">
                        {title && <div className="text-sm font-semibold text-gray-700">{title}</div>}
                        <div className="border rounded-md overflow-hidden">
                          <div className="p-4 bg-gray-50">
                            <pre className="text-xs overflow-auto max-h-96 whitespace-pre-wrap break-words font-mono">
                              {formatted}
                            </pre>
                          </div>
                        </div>
                      </div>
                    );
                  } catch (e) {
                    // If parsing fails, display as string
                    return (
                      <div className="space-y-2">
                        {title && <div className="text-sm font-semibold text-gray-700">{title}</div>}
                        <div className="border rounded-md overflow-hidden">
                          <div className="p-4 bg-gray-50">
                            <pre className="text-xs overflow-auto max-h-96 whitespace-pre-wrap break-words font-mono">
                              {payload}
                            </pre>
                          </div>
                        </div>
                      </div>
                    );
                  }
                }
                
                if (typeof payload !== 'object') return null;
                
                // For objects, stringify with formatting (JavaScript preserves key order)
                return (
                  <div className="space-y-2">
                    {title && <div className="text-sm font-semibold text-gray-700">{title}</div>}
                    <div className="border rounded-md overflow-hidden">
                      <div className="p-4 bg-gray-50">
                        <pre className="text-xs overflow-auto max-h-96 whitespace-pre-wrap break-words font-mono">
                          {JSON.stringify(payload, null, 2)}
                        </pre>
                      </div>
                    </div>
                  </div>
                );
              };
              
              const renderApiCall = (requestPayload, responsePayload, title) => {
                if (!requestPayload && !responsePayload) return null;
                
                return (
                  <div className="space-y-4 border-b pb-6 last:border-b-0 last:pb-0">
                    <div className="text-base font-semibold text-gray-800 border-b pb-2">{title}</div>
                    
                    {/* Request Payload */}
                    {requestPayload && (
                      renderPayloadJson(requestPayload, "Request (Sent to Cin7)")
                    )}
                    
                    {/* Response Payload */}
                    {responsePayload && (
                      renderPayloadJson(responsePayload, "Response (From Cin7)")
                    )}
                    
                    {!responsePayload && requestPayload && (
                      <div className="text-sm text-gray-500 italic">No response data available</div>
                    )}
                  </div>
                );
              };
              
              // Check if there's already a real API log for duplicate PO check
              const hasRealDuplicateCheckLog = apiLogs.some(log => 
                log.endpoint === '/saleList' && log.method === 'GET'
              );
              
              // Create a synthetic log entry for duplicate PO search only if:
              // 1. The duplicate_search_response exists in order_data
              // 2. There's no real API log for /saleList already (for backward compatibility)
              const duplicateSearchResponse = viewingOrderPayload?.order_data?.duplicate_search_response;
              const duplicateSearchLog = (duplicateSearchResponse && !hasRealDuplicateCheckLog) ? {
                id: 'duplicate-po-search',
                method: 'GET',
                endpoint: '/saleList',
                request_url: `/saleList?Search=${encodeURIComponent(duplicateSearchResponse.search_query)}`,
                request_body: { Search: duplicateSearchResponse.search_query },
                response_body: duplicateSearchResponse.all_sales_found || duplicateSearchResponse.duplicate_sales || [],
                response_status: 200,
                trigger: 'duplicate_po_check',
                duration_ms: null,
                created_at: new Date().toISOString()
              } : null;

              // Combine duplicate search log with API logs (duplicate search first)
              const allLogs = [];
              if (duplicateSearchLog) {
                allLogs.push(duplicateSearchLog);
              }
              allLogs.push(...apiLogs);

              return (
                <>
                  {/* API Logs from Database - Primary source of truth */}
                  <div className="space-y-4">
                    {loadingApiLogs ? (
                      <div className="text-sm text-gray-500">Loading API logs...</div>
                    ) : allLogs.length > 0 ? (
                      <div className="space-y-2">
                        {allLogs.map((log, idx) => {
                          const logId = log.id || `log-${idx}`;
                          const isExpanded = expandedLogIds.has(logId);
                          
                          return (
                            <div key={logId} className="border rounded-md overflow-hidden">
                              <div 
                                className="bg-gray-100 p-3 border-b cursor-pointer hover:bg-gray-200 transition-colors"
                                onClick={() => {
                                  const newExpanded = new Set(expandedLogIds);
                                  if (isExpanded) {
                                    newExpanded.delete(logId);
                                  } else {
                                    newExpanded.add(logId);
                                  }
                                  setExpandedLogIds(newExpanded);
                                }}
                              >
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    {isExpanded ? (
                                      <ChevronDown className="h-4 w-4 text-gray-600" />
                                    ) : (
                                      <ChevronRight className="h-4 w-4 text-gray-600" />
                                    )}
                                    <span className="font-semibold text-sm">{log.method}</span>
                                    <span className="text-xs text-gray-600">{log.endpoint}</span>
                                    {log.trigger && (
                                      <Badge variant="outline" className="text-xs">{log.trigger}</Badge>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-2">
                                    {log.response_status && (
                                      <Badge 
                                        variant={log.response_status >= 400 ? "destructive" : "default"}
                                        className="text-xs"
                                      >
                                        {log.response_status}
                                      </Badge>
                                    )}
                                    {log.duration_ms && (
                                      <span className="text-xs text-gray-500">{log.duration_ms}ms</span>
                                    )}
                                    {log.created_at && (
                                      <span className="text-xs text-gray-500">
                                        {new Date(log.created_at).toLocaleTimeString()}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                              {isExpanded && (
                                <div className="p-4 space-y-3">
                                  {/* Request */}
                                  {log.request_body && (
                                    <div>
                                      <div className="text-sm font-semibold text-gray-700 mb-2">Request (Sent to Cin7):</div>
                                      {renderPayloadJson(log.request_body, null)}
                                    </div>
                                  )}
                                  
                                  {/* Response */}
                                  {log.response_body && (
                                    <div>
                                      <div className="text-sm font-semibold text-gray-700 mb-2">Response (From Cin7):</div>
                                      {renderPayloadJson(log.response_body, null)}
                                    </div>
                                  )}
                                  
                                  {/* Additional info for duplicate PO search */}
                                  {log.id === 'duplicate-po-search' && duplicateSearchResponse && (
                                    <div className="p-2 bg-blue-50 rounded border border-blue-200">
                                      <div className="text-sm font-semibold text-blue-800 mb-1">Search Summary:</div>
                                      <div className="text-sm text-blue-700 space-y-1">
                                        <div>Search Query: <span className="font-mono">PO # {duplicateSearchResponse.search_query}</span></div>
                                        <div>Total found: {duplicateSearchResponse.total_found}</div>
                                        <div>Active duplicates: {duplicateSearchResponse.active_duplicates}</div>
                                        <div>Voided filtered: {duplicateSearchResponse.voided_filtered}</div>
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Error Message */}
                                  {log.error_message && (
                                    <div className="p-2 bg-red-50 rounded border border-red-200">
                                      <div className="text-sm font-semibold text-red-800 mb-1">Error:</div>
                                      <div className="text-sm text-red-700 break-words">{log.error_message}</div>
                                    </div>
                                  )}
                                  
                                  {/* Request URL */}
                                  {log.request_url && (
                                    <div className="text-xs text-gray-500 break-all">
                                      <span className="font-semibold">URL:</span> {log.request_url}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="text-sm text-gray-500 italic">
                        No API logs found for this order
                        {viewingOrderPayload?.id && (
                          <span className="ml-2">(Order ID: {viewingOrderPayload.id})</span>
                        )}
                        {!loadingApiLogs && (
                          <div className="mt-2 text-xs text-gray-400">
                            Check browser console for debug information
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </>
              );
            })()}
          </div>
        </DialogContent>
      </Dialog>
      
      {/* CSV View Modal */}
      <Dialog open={csvModalOpen} onOpenChange={setCsvModalOpen}>
        <DialogContent className="max-w-[95vw] max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              {csvFilename}
            </DialogTitle>
            <DialogDescription>
              Original CSV file content ({csvRows.length} rows)
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto border-[0.5px] rounded-md bg-white">
            {csvHeaders.length > 0 && csvRows.length > 0 ? (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-white z-10">
                    <TableRow>
                      <TableHead className="text-xs font-semibold w-16 sticky left-0 top-0 bg-white z-20 border-r">Row</TableHead>
                      {csvHeaders.map((header, idx) => (
                        <TableHead key={idx} className="text-xs font-semibold whitespace-nowrap min-w-[120px]">
                          {header}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {csvRows.map((row, rowIdx) => (
                      <TableRow key={rowIdx}>
                        <TableCell className="text-xs font-medium sticky left-0 bg-white z-10 border-r">
                          {row.rowNumber}
                        </TableCell>
                        {row.data.map((cell, cellIdx) => (
                          <TableCell key={cellIdx} className="text-xs whitespace-nowrap">
                            {cell || '-'}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <div className="p-4 text-center text-muted-foreground">
                No data to display
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 pt-4 border-t">
            <Button
              variant="outline"
              onClick={() => {
                if (viewingUploadId) {
                  window.open(`/webhooks/upload/${viewingUploadId}/csv`, '_blank');
                }
              }}
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <Button onClick={() => setCsvModalOpen(false)}>
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {/* Review Notes Modal */}
      <Dialog open={reviewModalOpen} onOpenChange={setReviewModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add Review Notes</DialogTitle>
            <DialogDescription>
              Please provide notes for this review. You can select a preset option or enter custom notes.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="preset-select">Preset Options (Optional)</Label>
              <Select value={reviewNotesPreset} onValueChange={(value) => {
                setReviewNotesPreset(value);
                setReviewNotes(value);
              }}>
                <SelectTrigger id="preset-select">
                  <SelectValue placeholder="Select a preset or leave blank for custom notes" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Manually adjusted in Cin7">Manually adjusted in Cin7</SelectItem>
                  <SelectItem value="Reviewed">Reviewed</SelectItem>
                  <SelectItem value="Issue resolved">Issue resolved</SelectItem>
                  <SelectItem value="No action needed">No action needed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="review-notes">Review Notes *</Label>
              <textarea
                id="review-notes"
                className="w-full min-h-[100px] px-3 py-2 text-sm border border-input rounded-md bg-transparent resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
                placeholder="Enter review notes or select a preset above"
                required
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => {
              setReviewModalOpen(false);
              setReviewNotes('');
              setReviewNotesPreset('');
            }}>
              Cancel
            </Button>
            <Button onClick={submitReview} disabled={!reviewNotes.trim()}>
              Submit Review
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bulk Review Notes Modal */}
      <Dialog open={bulkReviewModalOpen} onOpenChange={setBulkReviewModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              Add Review Notes ({bulkReviewIndex + 1} of {bulkReviewOrders.length})
            </DialogTitle>
            <DialogDescription>
              Reviewing: <strong>{bulkReviewOrders[bulkReviewIndex]?.order_key || 'N/A'}</strong>
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="bulk-preset-select">Preset Options (Optional)</Label>
              <Select value={reviewNotesPreset} onValueChange={(value) => {
                setReviewNotesPreset(value);
                setReviewNotes(value);
              }}>
                <SelectTrigger id="bulk-preset-select">
                  <SelectValue placeholder="Select a preset or leave blank for custom notes" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Manually adjusted in Cin7">Manually adjusted in Cin7</SelectItem>
                  <SelectItem value="Reviewed">Reviewed</SelectItem>
                  <SelectItem value="Issue resolved">Issue resolved</SelectItem>
                  <SelectItem value="No action needed">No action needed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="bulk-review-notes">Review Notes *</Label>
              <textarea
                id="bulk-review-notes"
                className="w-full min-h-[100px] px-3 py-2 text-sm border border-input rounded-md bg-transparent resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
                placeholder="Enter review notes or select a preset above"
                required
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => {
              setBulkReviewModalOpen(false);
              setReviewNotes('');
              setReviewNotesPreset('');
              setBulkReviewOrders([]);
              setBulkReviewIndex(0);
            }}>
              Cancel
            </Button>
            <Button onClick={submitBulkReview} disabled={!reviewNotes.trim()}>
              {bulkReviewIndex < bulkReviewOrders.length - 1 ? 'Next' : 'Finish'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default QueueView;

