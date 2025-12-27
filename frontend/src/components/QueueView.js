import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { ChevronDown, ChevronRight, RefreshCw, CheckCircle2, XCircle, Clock, FileText, RotateCcw, Eye, Download, Code, AlertCircle, CheckSquare, Square } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { cn } from '../lib/utils';

const QueueView = () => {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
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
  
  // Failed Orders tab state
  const [failedOrders, setFailedOrders] = useState([]);
  const [failedOrdersLoading, setFailedOrdersLoading] = useState(true);
  const [selectedOrderIds, setSelectedOrderIds] = useState(new Set());
  const [errorTypeFilter, setErrorTypeFilter] = useState('');
  const [expandedFailedOrders, setExpandedFailedOrders] = useState(new Set());
  
  // Completed Orders tab state
  const [completedOrders, setCompletedOrders] = useState([]);
  const [completedOrdersLoading, setCompletedOrdersLoading] = useState(true);
  const [expandedCompletedOrders, setExpandedCompletedOrders] = useState(new Set());

  const loadQueue = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/webhooks/queue');
      setUploads(response.data.uploads || []);
    } catch (error) {
      console.error('Failed to load queue:', error);
      if (error.response?.status === 401) {
        toast.error('Please log in to view the queue');
      } else {
        toast.error(`Failed to load queue: ${error.response?.data?.error || error.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadApiLogs = async (orderId) => {
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
  };

  // Load API logs when modal opens with an order
  useEffect(() => {
    if (jsonModalOpen && viewingOrderPayload) {
      // Try different possible ID fields - check all possible locations
      const orderId = viewingOrderPayload.id || 
                     viewingOrderPayload.order_result_id ||
                     (viewingOrderPayload.order_data && viewingOrderPayload.order_data.id);
      
      console.log('Modal opened with order payload:', viewingOrderPayload);
      console.log('Extracted order ID:', orderId);
      console.log('Available keys in viewingOrderPayload:', Object.keys(viewingOrderPayload || {}));
      
      if (orderId) {
        loadApiLogs(orderId);
      } else {
        console.warn('No order ID found in viewingOrderPayload. Available keys:', Object.keys(viewingOrderPayload || {}));
        console.warn('Full viewingOrderPayload:', JSON.stringify(viewingOrderPayload, null, 2));
        setApiLogs([]);
      }
    } else {
      setApiLogs([]);
    }
  }, [jsonModalOpen, viewingOrderPayload]);

  const loadFailedOrders = async () => {
    try {
      setFailedOrdersLoading(true);
      const response = await axios.get('/webhooks/orders/failed');
      setFailedOrders(response.data.failed_orders || []);
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

  const loadCompletedOrders = async () => {
    try {
      setCompletedOrdersLoading(true);
      const response = await axios.get('/webhooks/orders/completed');
      setCompletedOrders(response.data.completed_orders || []);
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

  useEffect(() => {
    loadQueue();
    loadFailedOrders();
    loadCompletedOrders();
    // Refresh every 30 seconds
    const interval = setInterval(() => {
      loadQueue();
      loadFailedOrders();
      loadCompletedOrders();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

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
      case 'completed':
        return <Badge variant="default" className="bg-green-500">Completed</Badge>;
      case 'processing':
        return <Badge variant="default" className="bg-blue-500">Processing</Badge>;
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>;
      case 'duplicate':
        return <Badge variant="secondary" className="bg-yellow-500 text-white">Duplicate</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
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
        loadQueue();
        loadFailedOrders();
      } else {
        toast.error(`Retry failed: ${response.data.error_message || 'Unknown error'}`);
        loadQueue();
        loadFailedOrders();
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
      loadQueue();
      loadFailedOrders();
    } catch (error) {
      console.error('Failed to bulk retry orders:', error);
      toast.error(error.response?.data?.error || 'Failed to bulk retry orders');
    }
  };

  const resolveOrder = async (orderId, reason = '') => {
    try {
      await axios.post(`/webhooks/orders/${orderId}/resolve`, { reason });
      toast.success('Order marked as resolved');
      loadFailedOrders();
    } catch (error) {
      console.error('Failed to resolve order:', error);
      toast.error(error.response?.data?.error || 'Failed to resolve order');
    }
  };

  const bulkResolveOrders = async () => {
    if (selectedOrderIds.size === 0) {
      toast.error('Please select at least one order');
      return;
    }
    
    try {
      const promises = Array.from(selectedOrderIds).map(id => 
        axios.post(`/webhooks/orders/${id}/resolve`, { reason: 'Bulk resolved' })
      );
      
      await Promise.all(promises);
      toast.success(`${selectedOrderIds.size} order(s) marked as resolved`);
      setSelectedOrderIds(new Set());
      loadFailedOrders();
    } catch (error) {
      console.error('Failed to bulk resolve orders:', error);
      toast.error('Failed to bulk resolve orders');
    }
  };

  const toggleSelectOrder = (orderId) => {
    const newSelected = new Set(selectedOrderIds);
    if (newSelected.has(orderId)) {
      newSelected.delete(orderId);
    } else {
      newSelected.add(orderId);
    }
    setSelectedOrderIds(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedOrderIds.size === failedOrders.length) {
      setSelectedOrderIds(new Set());
    } else {
      setSelectedOrderIds(new Set(failedOrders.map(o => o.id)));
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

  const getErrorTypeBadge = (errorType) => {
    if (!errorType) return null;
    
    const typeLabels = {
      'customer_not_found': 'Customer Not Found',
      'missing_fields': 'Missing Fields',
      'api_error': 'API Error',
      'validation_error': 'Validation Error'
    };
    
    const typeColors = {
      'customer_not_found': 'bg-red-500',
      'missing_fields': 'bg-orange-500',
      'api_error': 'bg-purple-500',
      'validation_error': 'bg-yellow-500'
    };
    
    return (
      <Badge className={cn(typeColors[errorType] || 'bg-gray-500', 'text-white')}>
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

  const renderPayloadTable = (payload, title, showOrderHeader = false, matchingDetails = null) => {
    if (!payload || typeof payload !== 'object') return null;
    
    // Check if it's a sale_order_payload (has Lines array)
    if (payload.Lines && Array.isArray(payload.Lines)) {
      return (
        <div className="space-y-3">
          {/* Order Details fields (non-Lines fields) - only show if showOrderHeader is true */}
          {showOrderHeader && Object.keys(payload).filter(k => k !== 'Lines').length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-700 mb-1">{title}</div>
              <div className="border-[0.5px] rounded-md overflow-hidden bg-white">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-gray-50">
                      <TableHead className="w-1/3 font-semibold text-xs">Field</TableHead>
                      <TableHead className="font-semibold text-xs">Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(payload)
                      .filter(([key]) => key !== 'Lines')
                      .map(([key, value]) => {
                        const isPlaceholder = typeof value === 'string' && (value.includes('<REQUIRED:') || value.includes('<SALE_ID_PLACEHOLDER>'));
                        const isEmpty = value === null || value === undefined || value === '';
                        const isMissing = isPlaceholder || isEmpty;
                        
                        // Special handling for Customer field
                        const isCustomerField = key === 'Customer' || key === 'customer_name';
                        const customerNotMatched = isCustomerField && matchingDetails?.customer && !matchingDetails.customer.found;
                        
                        return (
                          <TableRow key={key} className={`bg-white ${isMissing ? 'bg-orange-50' : ''}`}>
                            <TableCell className="font-medium text-xs text-gray-700 bg-white">{key}</TableCell>
                            <TableCell className={`text-xs bg-white ${customerNotMatched ? 'text-red-600' : isPlaceholder ? 'text-orange-600 font-medium italic' : isEmpty ? 'text-orange-600 italic' : 'text-gray-900'}`}>
                              <div className="flex items-center gap-1.5">
                                <span>{isPlaceholder ? value : (isEmpty ? <span className="italic">(missing)</span> : String(value))}</span>
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
            {payload.Lines.length > 0 ? (
              <div className="border rounded-md overflow-hidden bg-white">
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
                      {payload.Lines.map((line, idx) => {
                        const hasPlaceholder = line.ProductID && String(line.ProductID).includes('<REQUIRED:');
                        const missingProductId = !line.ProductID || hasPlaceholder;
                        const hasMissingFields = missingProductId || !line.SKU;
                        
                        // Find matching product details
                        const productMatch = matchingDetails?.products?.find(p => p.sku === line.SKU);
                        const isMatched = productMatch?.found && line.ProductID && !hasPlaceholder;
                        
                        return (
                          <TableRow key={idx} className={`bg-white ${hasMissingFields && !isMatched ? 'bg-orange-50' : ''}`}>
                            <TableCell className={`font-mono text-xs bg-white ${isMatched ? 'text-green-600' : !line.SKU ? 'text-orange-600 italic' : 'text-gray-900'}`}>
                              <div className="flex items-center gap-1.5">
                                <span>{line.SKU || <span className="italic">(missing)</span>}</span>
                                {isMatched && (
                                  <Badge variant="default" className="bg-green-500 text-[10px] px-1.5 py-0 h-4 !font-semibold hover:bg-green-500 font-sans">Matched</Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="text-right text-xs bg-white">{line.Quantity ?? '-'}</TableCell>
                            <TableCell className="text-right text-xs bg-white">{line.Price !== undefined ? `$${Number(line.Price).toFixed(2)}` : '-'}</TableCell>
                            <TableCell className="text-right text-xs bg-white">
                              {line.Quantity !== undefined && line.Price !== undefined 
                                ? `$${(Number(line.Quantity) * Number(line.Price)).toFixed(2)}` 
                                : '-'}
                            </TableCell>
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
      );
    } else {
      // Regular payload (sale_payload - order header only)
      return (
        <div>
          <div className="text-xs font-semibold text-gray-700 mb-1">{title}</div>
          <div className="border-[0.5px] rounded-md overflow-hidden bg-white">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50">
                  <TableHead className="w-1/3 font-semibold text-xs">Field</TableHead>
                  <TableHead className="font-semibold text-xs">Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(payload).map(([key, value]) => {
                  const isPlaceholder = typeof value === 'string' && (value.includes('<REQUIRED:') || value.includes('<SALE_ID_PLACEHOLDER>'));
                  const isEmpty = value === null || value === undefined || value === '';
                  const isMissing = isPlaceholder || isEmpty;
                  
                  // Special handling for Customer field
                  const isCustomerField = key === 'Customer' || key === 'customer_name';
                  const customerNotMatched = isCustomerField && matchingDetails?.customer && !matchingDetails.customer.found;
                  
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
      );
    }
  };

  return (
    <div className="h-full w-full overflow-y-auto">
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">Upload Queue</h1>
            <p className="text-xs text-muted-foreground mt-1">
              View order processing results from email webhooks
            </p>
          </div>
          <Button onClick={() => { loadQueue(); loadFailedOrders(); loadCompletedOrders(); }} disabled={loading || failedOrdersLoading || completedOrdersLoading} variant="outline">
            <RefreshCw className={cn("h-4 w-4 mr-2", (loading || failedOrdersLoading || completedOrdersLoading) && "animate-spin")} />
            Refresh
          </Button>
        </div>

        <Tabs defaultValue="failed" className="w-full">
          <TabsList className="h-9 p-1">
            <TabsTrigger value="failed" className="text-xs py-1.5 px-3">
              Failed Orders
              {failedOrders.length > 0 && (
                <Badge variant="destructive" className="ml-1.5 text-[10px] px-1.5 py-0 h-4">{failedOrders.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="completed" className="text-xs py-1.5 px-3">
              Completed Orders
              {completedOrders.length > 0 && (
                <Badge variant="default" className="ml-1.5 text-[10px] px-1.5 py-0 h-4 bg-green-500">{completedOrders.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="uploads" className="text-xs py-1.5 px-3">All Uploads</TabsTrigger>
          </TabsList>

          <TabsContent value="uploads">
            {/* Uploads Table */}
            <div className="overflow-x-auto">
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">Loading...</div>
          ) : uploads.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">No uploads found</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12"></TableHead>
                  <TableHead>Filename</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Orders</TableHead>
                  <TableHead className="text-right">Successful</TableHead>
                  <TableHead className="text-right">Failed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {uploads.map((upload) => {
                  const isExpanded = expandedUploads.has(upload.id);
                  const successfulOrders = upload.order_results?.filter(or => or.status === 'success') || [];
                  const failedOrders = upload.order_results?.filter(or => or.status === 'failed') || [];
                  
                  return (
                    <React.Fragment key={upload.id}>
                      <TableRow
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => toggleExpand(upload.id)}
                      >
                        <TableCell>
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </TableCell>
                        <TableCell>
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
                        <TableCell>{getStatusBadge(upload.status)}</TableCell>
                        <TableCell className="text-right">{upload.order_results?.length || 0}</TableCell>
                        <TableCell className="text-right text-green-600">{upload.successful_orders || 0}</TableCell>
                        <TableCell className="text-right text-red-600">{upload.failed_orders || 0}</TableCell>
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
                                              {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details)}
                                              {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details)}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {/* Failed Orders */}
                              {failedOrders.length > 0 && (
                                <div>
                                  <h4 className="font-semibold text-xs mb-1.5 flex items-center gap-2 text-red-600">
                                    <XCircle className="h-3.5 w-3.5" />
                                    Failed Orders ({failedOrders.length})
                                  </h4>
                                  <div className="space-y-2">
                                    {failedOrders.map((order) => (
                                      <div key={order.id} className="bg-red-50 border border-red-200 rounded p-3">
                                        <div className="space-y-3">
                                          {/* Order Header with Actions */}
                                          <div className="flex items-center justify-between">
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
                                          
                                          {/* Order Details */}
                                          {(order.sale_payload || order.sale_order_payload) && (
                                            <div className="space-y-2 max-h-[400px] overflow-y-auto">
                                              {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details)}
                                              {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details)}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {successfulOrders.length === 0 && failedOrders.length === 0 && (
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
          )}
        </div>
          </TabsContent>

          <TabsContent value="failed">
            {/* Failed Orders View */}
            <div className="space-y-4">
              {/* Bulk Actions */}
              <div className="flex items-center justify-end">
                {selectedOrderIds.size > 0 && (
                  <div className="flex items-center gap-2">
                    <Button onClick={bulkRetryOrders} variant="default" size="sm" className="h-7 text-xs px-2">
                      <RotateCcw className="h-3 w-3 mr-1.5" />
                      Retry ({selectedOrderIds.size})
                    </Button>
                    <Button onClick={bulkResolveOrders} variant="outline" size="sm" className="h-7 text-xs px-2">
                      Resolve ({selectedOrderIds.size})
                    </Button>
                  </div>
                )}
              </div>

              {/* Failed Orders Table */}
              <div className="overflow-x-auto">
                {failedOrdersLoading ? (
                  <div className="text-center py-8 text-muted-foreground">Loading...</div>
                ) : failedOrders.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">No failed orders found</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-10">
                          <button onClick={toggleSelectAll} className="p-0.5">
                            {selectedOrderIds.size === failedOrders.length ? (
                              <CheckSquare className="h-3.5 w-3.5" />
                            ) : (
                              <Square className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </TableHead>
                        <TableHead className="w-10"></TableHead>
                        <TableHead className="text-xs font-semibold">Order</TableHead>
                        <TableHead className="text-xs font-semibold">Customer</TableHead>
                        <TableHead className="text-xs font-semibold">PO #</TableHead>
                        <TableHead className="text-xs font-semibold">Error Type</TableHead>
                        <TableHead className="text-xs font-semibold">Retry Count</TableHead>
                        <TableHead className="text-xs font-semibold">Last Retry</TableHead>
                        <TableHead className="text-xs font-semibold">Source Upload</TableHead>
                        <TableHead className="text-xs font-semibold">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {failedOrders.map((order) => {
                        const isExpanded = expandedFailedOrders.has(order.id);
                        const isSelected = selectedOrderIds.has(order.id);
                        
                        return (
                          <React.Fragment key={order.id}>
                            <TableRow className="cursor-pointer hover:bg-muted/50">
                              <TableCell className="text-xs" onClick={(e) => { e.stopPropagation(); toggleSelectOrder(order.id); }}>
                                {isSelected ? (
                                  <CheckSquare className="h-3.5 w-3.5" />
                                ) : (
                                  <Square className="h-3.5 w-3.5" />
                                )}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {isExpanded ? (
                                  <ChevronDown className="h-3.5 w-3.5" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5" />
                                )}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                <span className="font-medium">{order.order_key}</span>
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {order.customer_name || '-'}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {order.po_number || '-'}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {getErrorTypeBadge(order.error_type)}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {order.retry_count || 0}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {order.last_retry_at ? formatDate(order.last_retry_at) : '-'}
                              </TableCell>
                              <TableCell className="text-xs" onClick={() => toggleExpandFailedOrder(order.id)}>
                                {order.upload ? (
                                  <div>
                                    <div className="font-medium">{order.upload.filename}</div>
                                    <div className="text-muted-foreground text-[10px]">{formatDate(order.upload.created_at)}</div>
                                  </div>
                                ) : '-'}
                              </TableCell>
                              <TableCell className="text-xs">
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
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-6 px-2 text-xs"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      resolveOrder(order.id);
                                    }}
                                  >
                                    Resolve
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                            {isExpanded && (
                              <TableRow>
                                <TableCell colSpan={10} className="bg-muted/30">
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
                                        {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details)}
                                        {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details)}
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
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="completed">
            {/* Completed Orders View */}
            <div className="space-y-4">
              {/* Completed Orders Table */}
              <div className="overflow-x-auto">
                {completedOrdersLoading ? (
                  <div className="text-center py-8 text-muted-foreground">Loading...</div>
                ) : completedOrders.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">No completed orders found</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12"></TableHead>
                        <TableHead>Order</TableHead>
                        <TableHead>Customer</TableHead>
                        <TableHead>PO #</TableHead>
                        <TableHead>Open in Cin7</TableHead>
                        <TableHead>Source Upload</TableHead>
                        <TableHead>Completed At</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {completedOrders.map((order) => {
                        const isExpanded = expandedCompletedOrders.has(order.id);
                        
                        return (
                          <React.Fragment key={order.id}>
                            <TableRow className="cursor-pointer hover:bg-muted/50">
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4" />
                                ) : (
                                  <ChevronRight className="h-4 w-4" />
                                )}
                              </TableCell>
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                <span className="font-medium">{order.order_key}</span>
                              </TableCell>
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                {order.customer_name || '-'}
                              </TableCell>
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                {order.po_number || '-'}
                              </TableCell>
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                {order.sale_id ? (
                                  <a
                                    href={`https://inventory.dearsystems.com/Sale#${order.sale_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="text-blue-600 hover:text-blue-800 hover:underline font-medium"
                                  >
                                    Open in Cin7
                                  </a>
                                ) : '-'}
                              </TableCell>
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                {order.upload ? (
                                  <div className="text-xs">
                                    <div className="font-medium">{order.upload.filename}</div>
                                    <div className="text-muted-foreground">{formatDate(order.upload.created_at)}</div>
                                  </div>
                                ) : '-'}
                              </TableCell>
                              <TableCell onClick={() => {
                                const newExpanded = new Set(expandedCompletedOrders);
                                if (newExpanded.has(order.id)) {
                                  newExpanded.delete(order.id);
                                } else {
                                  newExpanded.add(order.id);
                                }
                                setExpandedCompletedOrders(newExpanded);
                              }}>
                                {formatDate(order.processed_at)}
                              </TableCell>
                            </TableRow>
                            {isExpanded && (
                              <TableRow>
                                <TableCell colSpan={8} className="bg-muted/30">
                                  <div className="p-4 space-y-4">
                                    {/* Success Message */}
                                    <div>
                                      <div className="font-semibold text-sm mb-2 text-green-600">✓ Successfully Created in Cin7</div>
                                      <div className="text-sm bg-green-50 p-3 rounded border border-green-200">
                                        {order.sale_id && (
                                          <div className="mb-2">
                                            <span className="font-medium">Sale ID:</span> {order.sale_id}
                                          </div>
                                        )}
                                        {order.sale_order_id && (
                                          <div>
                                            <span className="font-medium">Sale Order ID:</span> {order.sale_order_id}
                                          </div>
                                        )}
                                      </div>
                                    </div>

                                    {/* Order Details - reuse existing renderPayloadTable */}
                                    {(order.sale_payload || order.sale_order_payload) && (
                                      <div>
                                        <div className="font-semibold text-sm mb-2">Created Payload</div>
                                        <div className="space-y-3 max-h-[500px] overflow-y-auto">
                                          {order.sale_payload && renderPayloadTable(order.sale_payload, "Order Details", false, order.matching_details)}
                                          {order.sale_order_payload && renderPayloadTable(order.sale_order_payload, "Line Items", false, order.matching_details)}
                                        </div>
                                      </div>
                                    )}

                                    {/* Matching Details */}
                                    {order.matching_details && (
                                      <div>
                                        <div className="font-semibold text-sm mb-2 text-gray-700">Matching Details</div>
                                        <div className="border rounded-md overflow-hidden bg-white">
                                          <Table>
                                            <TableHeader>
                                              <TableRow className="bg-gray-50">
                                                <TableHead className="w-1/3 font-semibold text-xs">Item</TableHead>
                                                <TableHead className="font-semibold text-xs">Status</TableHead>
                                              </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                              <TableRow>
                                                <TableCell className="text-xs bg-white">Customer</TableCell>
                                                <TableCell className="text-xs bg-white">
                                                  {order.matching_details.customer?.found ? (
                                                    <span className="text-green-600">✓ Found (ID: {order.matching_details.customer.cin7_id})</span>
                                                  ) : (
                                                    <span className="text-red-600">✗ {order.matching_details.customer?.error || 'Not found'}</span>
                                                  )}
                                                </TableCell>
                                              </TableRow>
                                              {order.matching_details.products?.map((product, idx) => (
                                                <TableRow key={idx}>
                                                  <TableCell className="text-xs bg-white">SKU {product.sku}</TableCell>
                                                  <TableCell className="text-xs bg-white">
                                                    {product.found ? (
                                                      <span className="text-green-600">✓ Found (ID: {product.cin7_id})</span>
                                                    ) : (
                                                      <span className="text-red-600">✗ {product.error || 'Not found'}</span>
                                                    )}
                                                  </TableCell>
                                                </TableRow>
                                              ))}
                                            </TableBody>
                                          </Table>
                                        </div>
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
              Order Payload Details
            </DialogTitle>
            <DialogDescription>
              {viewingOrderPayload?.order_data?.attempted_send === false 
                ? "Prepared payloads (not sent to Cin7)" 
                : "Payloads sent to Cin7"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-auto space-y-6 p-4">
            {viewingOrderPayload?.order_data?.attempted_send === false && (
              <div className="p-3 bg-yellow-50 rounded border border-yellow-200 text-sm text-yellow-800">
                <strong>Note:</strong> These payloads were not sent to Cin7 because the customer was not found.
              </div>
            )}
            
            {/* All Error Messages */}
            {(() => {
              const errors = [];
              
              // Main error message
              if (viewingOrderPayload?.error_message) {
                errors.push({
                  source: 'Main Error',
                  message: viewingOrderPayload.error_message
                });
              }
              
              // Error from order_data
              if (viewingOrderPayload?.order_data?.error_message) {
                errors.push({
                  source: 'Order Data Error',
                  message: viewingOrderPayload.order_data.error_message
                });
              }
              
              // Matching details errors
              if (viewingOrderPayload?.order_data?.matching_details) {
                const md = viewingOrderPayload.order_data.matching_details;
                
                // Customer errors
                if (md.customer && !md.customer.found && md.customer.error) {
                  errors.push({
                    source: 'Customer Matching',
                    message: md.customer.error
                  });
                }
                
                // Product errors
                if (md.products && Array.isArray(md.products)) {
                  md.products.forEach((product, idx) => {
                    if (!product.found && product.error) {
                      errors.push({
                        source: `Product ${idx + 1} (${product.sku || 'Unknown'})`,
                        message: product.error
                      });
                    }
                  });
                }
                
                // Missing fields
                if (md.missing_fields && Array.isArray(md.missing_fields) && md.missing_fields.length > 0) {
                  errors.push({
                    source: 'Missing Required Fields',
                    message: `Missing: ${md.missing_fields.join(', ')}`
                  });
                }
              }
              
              // API response errors - check if response is an array of error objects
              if (viewingOrderPayload?.sale_api_response) {
                const saleResp = viewingOrderPayload.sale_api_response;
                if (Array.isArray(saleResp)) {
                  // Array of error objects
                  saleResp.forEach((errorObj, idx) => {
                    if (errorObj.ErrorCode || errorObj.Exception || errorObj.Message) {
                      errors.push({
                        source: `Sale API Error ${idx + 1}`,
                        message: errorObj.Exception || errorObj.Message || `ErrorCode: ${errorObj.ErrorCode}` || 'Unknown API error',
                        fullError: errorObj
                      });
                    }
                  });
                } else if (typeof saleResp === 'object') {
                  // Single error object
                  if (saleResp.Exception || saleResp.Message || saleResp.ErrorCode) {
                    errors.push({
                      source: 'Sale API Response',
                      message: saleResp.Exception || saleResp.Message || saleResp.ErrorCode || 'Unknown API error',
                      fullError: saleResp
                    });
                  }
                }
              }
              
              if (viewingOrderPayload?.sale_order_api_response) {
                const soResp = viewingOrderPayload.sale_order_api_response;
                if (Array.isArray(soResp)) {
                  // Array of error objects
                  soResp.forEach((errorObj, idx) => {
                    if (errorObj.ErrorCode || errorObj.Exception || errorObj.Message) {
                      errors.push({
                        source: `Sale Order API Error ${idx + 1}`,
                        message: errorObj.Exception || errorObj.Message || `ErrorCode: ${errorObj.ErrorCode}` || 'Unknown API error',
                        fullError: errorObj
                      });
                    }
                  });
                } else if (typeof soResp === 'object') {
                  // Single error object
                  if (soResp.Exception || soResp.Message || soResp.ErrorCode) {
                    errors.push({
                      source: 'Sale Order API Response',
                      message: soResp.Exception || soResp.Message || soResp.ErrorCode || 'Unknown API error',
                      fullError: soResp
                    });
                  }
                }
              }
              
              return errors.length > 0 ? (
                <div className="p-3 bg-red-50 rounded border border-red-200 space-y-3">
                  <div className="text-sm font-semibold text-red-800 mb-2">All Error Messages:</div>
                  {errors.map((error, idx) => (
                    <div key={idx} className="text-sm text-red-700 break-words">
                      <div className="font-medium mb-1">{error.source}:</div>
                      <div className="ml-2">{error.message}</div>
                      {error.fullError && (
                        <div className="ml-2 mt-1 p-2 bg-red-100 rounded border border-red-300">
                          <pre className="text-xs overflow-auto whitespace-pre-wrap break-words font-mono">
                            {JSON.stringify(error.fullError, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : null;
            })()}
            
            {/* Helper function to render payload as JSON */}
            {(() => {
              const renderPayloadJson = (payload, title) => {
                if (!payload || typeof payload !== 'object') return null;
                
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
              
              return (
                <>
                  {/* API Logs from Database - Primary source of truth */}
                  <div className="space-y-4">
                    <div className="text-base font-semibold text-gray-800 border-b pb-2">
                      API Calls (from Database)
                      {loadingApiLogs && <span className="text-sm text-gray-500 ml-2">(Loading...)</span>}
                    </div>
                    {loadingApiLogs ? (
                      <div className="text-sm text-gray-500">Loading API logs...</div>
                    ) : apiLogs.length > 0 ? (
                      <div className="space-y-2">
                        {apiLogs.map((log, idx) => {
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
          <div className="flex justify-end gap-2 pt-4 border-t">
            <Button onClick={() => setJsonModalOpen(false)}>
              Close
            </Button>
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
                      <TableHead className="text-xs font-semibold w-16 sticky left-0 bg-white z-20 border-r">Row</TableHead>
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
    </div>
  );
};

export default QueueView;

