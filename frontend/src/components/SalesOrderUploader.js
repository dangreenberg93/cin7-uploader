import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Upload, FileText, CheckCircle2, Check, XCircle, Loader2, Play, AlertCircle, Settings, Map, Code2, RotateCcw, RefreshCw } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { cn } from '../lib/utils';
import { useClient } from '../contexts/ClientContext';
import { useActivityLog } from '../contexts/ActivityLogContext';
import { useConnection } from '../contexts/ConnectionContext';

const SalesOrderUploader = ({ user }) => {
  const { selectedClientId, selectedClient } = useClient();
  const { connected, setConnected, credentials, setCredentials, setTestConnection } = useConnection();
  
  // Check if user is admin
  const isAdmin = user && (user.role === 'admin' || user.email === 'dan@paleblue.nyc');
  
  // Upload state - with localStorage persistence
  const [sessionId, setSessionId] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_sessionId');
    return saved || null;
  });
  const [csvColumns, setCsvColumns] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_csvColumns');
    const columns = saved ? JSON.parse(saved) : [];
    // Filter out empty strings and null values
    return columns.filter(col => col != null && String(col).trim().length > 0);
  });
  const [csvRows, setCsvRows] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_csvRows');
    return saved ? JSON.parse(saved) : [];
  });
  const [detectedMappings, setDetectedMappings] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_detectedMappings');
    return saved ? JSON.parse(saved) : {};
  });
  const [columnMapping, setColumnMapping] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_columnMapping');
    const mapping = saved ? JSON.parse(saved) : {};
    // Clean up any empty string values
    const cleaned = {};
    Object.keys(mapping).forEach(key => {
      const val = mapping[key];
      if (val != null && String(val).trim().length > 0) {
        cleaned[key] = String(val).trim();
      }
    });
    return cleaned;
  });
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [templateAutoLoaded, setTemplateAutoLoaded] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_templateAutoLoaded');
    return saved === 'true';
  });
  const [loadedTemplateName, setLoadedTemplateName] = useState(() => {
    return localStorage.getItem('salesOrderUploader_loadedTemplateName') || null;
  });
  
  // Validation state
  const [validating, setValidating] = useState(false);
  const [refreshingCache, setRefreshingCache] = useState(false);
  const [validationResults, setValidationResults] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_validationResults');
    return saved ? JSON.parse(saved) : null;
  });
  const [expandedRows, setExpandedRows] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_expandedRows');
    return saved ? new Set(JSON.parse(saved)) : new Set();
  });
  const [showPayloadRows, setShowPayloadRows] = useState(new Set());
  const [openPayloadModal, setOpenPayloadModal] = useState(null); // Track which row's payload modal is open
  
  // Processing state
  const [processing, setProcessing] = useState(false);
  const [processingResults, setProcessingResults] = useState(() => {
    const saved = localStorage.getItem('salesOrderUploader_processingResults');
    return saved ? JSON.parse(saved) : null;
  });

  // Persist state to localStorage whenever it changes
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('salesOrderUploader_sessionId', sessionId);
    } else {
      localStorage.removeItem('salesOrderUploader_sessionId');
    }
  }, [sessionId]);

  useEffect(() => {
    // Filter out empty strings before saving
    const filteredColumns = csvColumns.filter(col => col != null && String(col).trim().length > 0);
    if (filteredColumns.length > 0) {
      localStorage.setItem('salesOrderUploader_csvColumns', JSON.stringify(filteredColumns));
    } else {
      localStorage.removeItem('salesOrderUploader_csvColumns');
    }
  }, [csvColumns]);

  useEffect(() => {
    if (csvRows.length > 0) {
      localStorage.setItem('salesOrderUploader_csvRows', JSON.stringify(csvRows));
    } else {
      localStorage.removeItem('salesOrderUploader_csvRows');
    }
  }, [csvRows]);

  useEffect(() => {
    if (Object.keys(detectedMappings).length > 0) {
      localStorage.setItem('salesOrderUploader_detectedMappings', JSON.stringify(detectedMappings));
    } else {
      localStorage.removeItem('salesOrderUploader_detectedMappings');
    }
  }, [detectedMappings]);

  useEffect(() => {
    if (Object.keys(columnMapping).length > 0) {
      localStorage.setItem('salesOrderUploader_columnMapping', JSON.stringify(columnMapping));
    } else {
      localStorage.removeItem('salesOrderUploader_columnMapping');
    }
  }, [columnMapping]);

  useEffect(() => {
    localStorage.setItem('salesOrderUploader_templateAutoLoaded', templateAutoLoaded.toString());
  }, [templateAutoLoaded]);

  useEffect(() => {
    if (loadedTemplateName) {
      localStorage.setItem('salesOrderUploader_loadedTemplateName', loadedTemplateName);
    } else {
      localStorage.removeItem('salesOrderUploader_loadedTemplateName');
    }
  }, [loadedTemplateName]);

  useEffect(() => {
    if (validationResults) {
      localStorage.setItem('salesOrderUploader_validationResults', JSON.stringify(validationResults));
    } else {
      localStorage.removeItem('salesOrderUploader_validationResults');
    }
  }, [validationResults]);

  useEffect(() => {
    if (expandedRows.size > 0) {
      localStorage.setItem('salesOrderUploader_expandedRows', JSON.stringify(Array.from(expandedRows)));
    } else {
      localStorage.removeItem('salesOrderUploader_expandedRows');
    }
  }, [expandedRows]);

  useEffect(() => {
    if (processingResults) {
      localStorage.setItem('salesOrderUploader_processingResults', JSON.stringify(processingResults));
    } else {
      localStorage.removeItem('salesOrderUploader_processingResults');
    }
  }, [processingResults]);
  
  // Terminal/logs
  const terminalEndRef = useRef(null);
  const testConnectionRef = useRef(false);
  const { addTerminalLine, setTerminalLines, terminalLines } = useActivityLog();
  
  // Mapping templates
  const [mappingTemplates, setMappingTemplates] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showMappingDialog, setShowMappingDialog] = useState(false);
  const autoSaveTimeoutRef = useRef(null);

  const resetUpload = () => {
    // Clear any pending auto-save
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }
    setSessionId(null);
    setCsvColumns([]);
    setCsvRows([]);
    setDetectedMappings({});
    setColumnMapping({});
    setValidationResults(null);
    setProcessingResults(null);
    setTemplateAutoLoaded(false);
    setLoadedTemplateName(null);
    setExpandedRows(new Set());
    setTerminalLines([]);
    
    // Clear localStorage
    localStorage.removeItem('salesOrderUploader_sessionId');
    localStorage.removeItem('salesOrderUploader_csvColumns');
    localStorage.removeItem('salesOrderUploader_csvRows');
    localStorage.removeItem('salesOrderUploader_detectedMappings');
    localStorage.removeItem('salesOrderUploader_columnMapping');
    localStorage.removeItem('salesOrderUploader_templateAutoLoaded');
    localStorage.removeItem('salesOrderUploader_loadedTemplateName');
    localStorage.removeItem('salesOrderUploader_validationResults');
    localStorage.removeItem('salesOrderUploader_expandedRows');
    localStorage.removeItem('salesOrderUploader_processingResults');
  };

  // Track previous client ID to only reset when it actually changes
  const prevClientIdRef = useRef(selectedClientId);
  const isInitialMount = useRef(true);
  
  useEffect(() => {
    if (selectedClientId) {
      loadClientDetails();
      loadMappingTemplates();
      
      // Only reset upload state if client actually changed (not on initial mount or hot reload)
      if (!isInitialMount.current && prevClientIdRef.current !== selectedClientId && prevClientIdRef.current !== null) {
        resetUpload();
      }
      prevClientIdRef.current = selectedClientId;
    } else {
      setCredentials(null);
      setConnected(false);
      if (!isInitialMount.current && prevClientIdRef.current !== null) {
        resetUpload();
      }
      prevClientIdRef.current = selectedClientId;
    }
    
    // Mark that initial mount is complete
    if (isInitialMount.current) {
      isInitialMount.current = false;
    }
  }, [selectedClientId]);

  useEffect(() => {
    // Auto-scroll terminal
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalLines]);


  const loadClientDetails = async () => {
    try {
      console.log(`[loadClientDetails] Loading credentials for client: ${selectedClientId}`);
      const credsRes = await axios.get(`/credentials/clients/${selectedClientId}`).catch(() => ({ data: null }));
      
      if (credsRes && credsRes.data && credsRes.data.application_key) {
        setCredentials(credsRes.data);
        // Test connection
        console.log(`[loadClientDetails] Credentials found, calling testConnection()`);
        await testConnection();
      } else {
        setCredentials(null);
        addTerminalLine('warning', 'Cin7 credentials not configured for this client');
        setConnected(false);
      }
    } catch (error) {
      console.error(`[loadClientDetails] Error:`, error);
      if (error.response?.status === 404) {
        addTerminalLine('warning', 'Cin7 credentials not configured');
        setCredentials(null);
      } else {
        addTerminalLine('error', `Failed to load client details: ${error.message}`);
      }
      setConnected(false);
    }
  };

  const testConnection = useCallback(async () => {
    try {
      console.log(`[testConnection] Calling /credentials/clients/${selectedClientId}/test`);
      addTerminalLine('info', 'Testing Cin7 connection...');
      const response = await axios.post(`/credentials/clients/${selectedClientId}/test`);
      console.log(`[testConnection] Response:`, response.data);
      
      if (response.data.success) {
        setConnected(true);
        addTerminalLine('success', 'Connected to Cin7 API');
        toast.success('Connected to Cin7');
      } else {
        setConnected(false);
        addTerminalLine('error', response.data.message || 'Connection test failed');
        toast.error('Connection test failed');
      }
    } catch (error) {
      console.error(`[testConnection] Error:`, error);
      console.error(`[testConnection] Error response:`, error.response?.data);
      setConnected(false);
      addTerminalLine('error', `Connection test failed: ${error.message}`);
      toast.error('Connection test failed');
    }
  }, [selectedClientId, setConnected, addTerminalLine]);

  // Expose testConnection to context
  useEffect(() => {
    setTestConnection(() => testConnection);
  }, [testConnection, setTestConnection]);

  const loadMappingTemplates = async () => {
    try {
      const response = await axios.get(`/sales/mapping/templates/${selectedClientId}`);
      setMappingTemplates(response.data);
    } catch (error) {
      console.error('Failed to load mapping templates:', error);
    }
  };

  const handleFileSelect = async (file) => {
    if (!selectedClientId) {
      toast.error('Please select a client first');
      return;
    }

    setUploading(true);
    addTerminalLine('info', `Uploading ${file.name}...`);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('client_id', selectedClientId);

      const response = await axios.post('/sales/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setSessionId(response.data.session_id);
      // Filter out empty strings from CSV columns
      const filteredColumns = (response.data.csv_columns || []).filter(col => col != null && String(col).trim().length > 0);
      setCsvColumns(filteredColumns);
      setDetectedMappings(response.data.detected_mappings);
      
      // Use auto-detected mapping from backend (includes default template if available)
      // Note: Backend already stores this in the session, so we don't need to save it again
      const initialMapping = response.data.initial_mapping || {};
      setColumnMapping(initialMapping);
      
      // Fetch CSV rows for preview
      try {
        const rowsResponse = await axios.get(`/sales/rows?session_id=${response.data.session_id}`);
        setCsvRows(rowsResponse.data.rows || []);
      } catch (error) {
        console.error('Failed to load CSV rows:', error);
      }

      if (response.data.default_mapping_loaded) {
        setTemplateAutoLoaded(true);
        setLoadedTemplateName(response.data.template_name || 'Default');
        addTerminalLine('success', `File uploaded: ${response.data.row_count} rows detected. Template "${response.data.template_name || 'Default'}" auto-applied.`);
        toast.success(`File uploaded: ${response.data.row_count} rows (template auto-applied)`);
      } else {
        setTemplateAutoLoaded(false);
        setLoadedTemplateName(null);
        addTerminalLine('success', `File uploaded: ${response.data.row_count} rows detected`);
        toast.success(`File uploaded: ${response.data.row_count} rows`);
      }
    } catch (error) {
      addTerminalLine('error', `Upload failed: ${error.response?.data?.error || error.message}`);
      toast.error('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = Array.from(e.dataTransfer.files);
    const csvFile = files.find(f => f.name.endsWith('.csv'));
    
    if (csvFile) {
      handleFileSelect(csvFile);
    } else {
      toast.error('Please upload a CSV file');
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const saveMapping = async (asTemplate = false) => {
    if (!sessionId) return;

    try {
      await axios.post('/sales/mapping', {
        session_id: sessionId,
        column_mapping: columnMapping,
        save_as_template: asTemplate,
        template_name: 'default',
        is_default: true
      });
      
      toast.success('Mapping saved');
      if (asTemplate) {
        loadMappingTemplates();
      }
    } catch (error) {
      toast.error('Failed to save mapping');
    }
  };

  const loadTemplate = (template) => {
    setColumnMapping(template.column_mapping);
    toast.success(`Loaded template: ${template.name}`);
  };

  const refreshCache = async () => {
    if (!selectedClientId) {
      toast.error('Please select a client');
      return;
    }

    if (!connected) {
      toast.error('Please ensure Cin7 connection is established');
      return;
    }

    setRefreshingCache(true);
    addTerminalLine('info', 'Refreshing customer and product cache from Cin7...');

    try {
      const response = await axios.post('/sales/refresh-cache', { 
        client_id: selectedClientId 
      });

      addTerminalLine('success', `Cache refreshed: ${response.data.customer_count} customers, ${response.data.product_count} products`);
      toast.success(
        `Cache refreshed: ${response.data.customer_count} customers, ${response.data.product_count} products`,
        { duration: 5000 }
      );
    } catch (error) {
      addTerminalLine('error', `Cache refresh failed: ${error.response?.data?.error || error.message}`);
      toast.error(error.response?.data?.error || 'Failed to refresh cache');
    } finally {
      setRefreshingCache(false);
    }
  };

  const validateData = async () => {
    if (!sessionId) {
      toast.error('Please upload a CSV file first');
      return;
    }

    if (!connected) {
      toast.error('Please ensure Cin7 connection is established');
      return;
    }

    setValidating(true);
    
    addTerminalLine('info', 'Validating data against Cin7 API...');

    try {
      // Send column mapping with validation request to avoid separate save step
      const response = await axios.post('/sales/validate', { 
        session_id: sessionId,
        column_mapping: columnMapping  // Include mapping in validation request
      });

      setValidationResults({
        validCount: response.data.valid_count,
        invalidCount: response.data.invalid_count,
        validRows: response.data.valid_rows || [],
        invalidRows: response.data.invalid_rows || [],
        customerCount: response.data.customer_count,
        productCount: response.data.product_count
      });

      if (response.data.invalid_count > 0) {
        addTerminalLine('warning', `Validation complete: ${response.data.valid_count} valid, ${response.data.invalid_count} invalid`);
        toast.warning(`${response.data.invalid_count} rows have errors`);
      } else {
        addTerminalLine('success', `All ${response.data.valid_count} rows are valid`);
        toast.success('All rows validated successfully');
      }
    } catch (error) {
      addTerminalLine('error', `Validation failed: ${error.response?.data?.error || error.message}`);
      toast.error('Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const toggleRowExpansion = (rowNumber) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(rowNumber)) {
        next.delete(rowNumber);
      } else {
        next.add(rowNumber);
      }
      return next;
    });
  };

  const renderJsonPayload = (row) => {
    if (!row || !row.preview_payload) {
      return (
        <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-md">
          <p className="text-sm text-yellow-800">
            Preview payload not available. This will be generated when creating orders.
          </p>
        </div>
      );
    }

    const payloads = row.preview_payload;
    const isVisible = showPayloadRows.has(row.row_number);
    
    // Handle both old format (single payload) and new format (sale + sale_order)
    const hasError = payloads.error;
    const salePayload = payloads.sale || (hasError ? null : payloads);
    const saleOrderPayload = payloads.sale_order;

    return (
      <div className="mt-4">
        {isVisible && (
          <>
            {hasError ? (
              <div className="border rounded-md overflow-hidden bg-red-50 p-4">
                <p className="text-sm text-red-800">{payloads.error}</p>
              </div>
            ) : (
              <>
                {payloads.customer_creation && (
                  <div className="mb-4">
                    <h6 className="text-xs font-semibold mb-2 text-blue-700">Customer Creation Payload (Before Step 1)</h6>
                    <div className="border rounded-md overflow-hidden bg-blue-50">
                      <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                        <code>{JSON.stringify(payloads.customer_creation, null, 2)}</code>
                      </pre>
                                    <p className="p-2 text-xs text-blue-700 bg-blue-100">
                                      This customer will be created first. The Sale payload will reference the CustomerID returned from the customer creation, along with the Customer name.
                                    </p>
                    </div>
                  </div>
                )}
                {salePayload && (
                  <div className="mb-4">
                    <h6 className="text-xs font-semibold mb-2 text-gray-700">Sale Payload (Step 1)</h6>
                    <div className="border rounded-md overflow-hidden bg-gray-50">
                      <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                        <code>{JSON.stringify(salePayload, null, 2)}</code>
                      </pre>
                    </div>
                  </div>
                )}
                {saleOrderPayload && (
                  <div>
                    <h6 className="text-xs font-semibold mb-2 text-gray-700">Sale Order Payload (Step 2)</h6>
                    <div className="border rounded-md overflow-hidden bg-gray-50">
                      <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                        <code>{JSON.stringify(saleOrderPayload, null, 2)}</code>
                      </pre>
                    </div>
                  </div>
                )}
              </>
            )}
            <div className="mt-2 text-xs text-muted-foreground">
              {payloads.customer_creation 
                ? 'These are the JSON payloads that will be sent to Cin7 API. First the customer will be created, then the Sale will reference the returned CustomerID and Customer name, then the Sale Order will be created.'
                : 'These are the JSON payloads that will be sent to Cin7 API. First the Sale is created, then the Sale Order is created with the Sale ID.'}
            </div>
          </>
        )}
      </div>
    );
  };

  const renderPreparedData = (row) => {
    if (!row) return null;

    let fieldStatus = row.field_status || {};
    const mappedData = row.mapped_data || {};
    
    // If field_status is missing, build it from mapped_data
    if (!row.field_status && row.mapped_data) {
      const requiredFields = ['CustomerName', 'CustomerReference', 'SaleDate', 'SKU', 'Price'];
      const optionalFields = ['Currency', 'TaxInclusive', 'ProductName', 'Quantity', 'Discount', 'Tax', 'Notes'];
      
      [...requiredFields, ...optionalFields].forEach(field => {
        const value = mappedData[field];
        const isRequired = requiredFields.includes(field);
        const hasError = row.errors?.some(e => e.includes(field) || e.toLowerCase().includes(field.toLowerCase()));
        
        if (!fieldStatus[field]) {
          if (value) {
            fieldStatus[field] = {
              status: hasError ? 'invalid' : 'ready',
              value: value,
              source: 'mapped',
              message: hasError ? (row.errors.find(e => e.includes(field)) || 'Has error') : 'Mapped and ready'
            };
          } else {
            fieldStatus[field] = {
              status: isRequired ? 'missing' : 'optional',
              value: null,
              source: null,
              message: isRequired ? 'Required field not mapped' : 'Optional field'
            };
          }
        }
      });
    }
    
    const fields = [
      { key: 'CustomerName', label: 'Customer Name', required: true },
      { key: 'CustomerReference', label: 'Customer Reference (PO#)', required: true },
      { key: 'SaleDate', label: 'Sale Date', required: true },
      { key: 'Currency', label: 'Currency', required: false },
      { key: 'SKU', label: 'Product SKU', required: true },
      { key: 'Quantity', label: 'Quantity', required: false },
      { key: 'Price', label: 'Price', required: true },
      { key: 'Discount', label: 'Discount', required: false },
      { key: 'Tax', label: 'Tax', required: false },
      { key: 'Notes', label: 'Notes', required: false },
    ];

    if (Object.keys(fieldStatus).length === 0) {
      return null;
    }

    return (
      <div className="mt-4">
        <h5 className="text-sm font-semibold mb-3 text-gray-700">Prepared Data for Cin7</h5>
        <div className="border rounded-md overflow-hidden bg-white">
          <Table className="border-0">
            <TableHeader>
              <TableRow className="bg-white">
                <TableHead className="w-48 bg-white">Cin7 Field</TableHead>
                <TableHead className="w-32 bg-white">Status</TableHead>
                <TableHead className="bg-white">Value</TableHead>
                <TableHead className="w-40 bg-white">Source</TableHead>
                <TableHead className="bg-white">Message</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fields.map((field) => {
                const status = fieldStatus[field.key] || { status: 'missing', value: null, source: null, message: 'Not mapped' };
                
                // Skip optional fields that aren't mapped
                if (!field.required && (status.status === 'optional' || status.status === 'missing') && !status.value) {
                  return null;
                }
                
                const statusTextColors = {
                  ready: 'text-green-600',
                  missing: 'text-red-600',
                  invalid: 'text-red-600',
                  optional: 'text-muted-foreground'
                };

                return (
                  <TableRow key={field.key} className="bg-white">
                    <TableCell className="font-medium bg-white text-xs">
                      {field.label}
                      {field.required && <span className="text-destructive ml-1">*</span>}
                    </TableCell>
                    <TableCell className="bg-white">
                      <span className={`text-xs font-medium ${statusTextColors[status.status] || statusTextColors.optional}`}>
                        {status.status === 'ready' ? 'Ready' : 
                         status.status === 'missing' ? 'Missing' :
                         status.status === 'invalid' ? 'Invalid' : 'Optional'}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-xs bg-white">
                      <div className="truncate text-xs">
                        {status.value ? String(status.value) : <span className="text-muted-foreground">-</span>}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground bg-white">
                      {status.source || '-'}
                    </TableCell>
                    <TableCell className={`text-xs bg-white ${status.status === 'invalid' ? 'text-red-600' : 'text-muted-foreground'}`}>
                      {status.message || '-'}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        <div className="mb-4"></div>
      </div>
    );
  };

  const createSalesOrders = async () => {
    if (!sessionId) {
      toast.error('Please upload a CSV file first');
      return;
    }

    if (!validationResults || validationResults.invalidCount > 0) {
      toast.error('Please fix validation errors before creating orders');
      return;
    }

    setProcessing(true);
    addTerminalLine('info', 'Creating sales orders in Cin7...');

    try {
      const response = await axios.post('/sales/create', { session_id: sessionId });

      setProcessingResults({
        successful: response.data.successful,
        failed: response.data.failed,
        uploadId: response.data.upload_id
      });

      addTerminalLine('success', `Created ${response.data.successful} sales orders`);
      if (response.data.failed > 0) {
        addTerminalLine('warning', `${response.data.failed} orders failed`);
      }
      toast.success(`Created ${response.data.successful} sales orders`);
    } catch (error) {
      addTerminalLine('error', `Failed to create orders: ${error.response?.data?.error || error.message}`);
      toast.error('Failed to create sales orders');
    } finally {
      setProcessing(false);
    }
  };

  // Cin7 field options
  // Note: CustomerID, CustomerCode, CustomerEmail, SaleOrderNumber, InvoiceNumber, Status, Location
  // are auto-generated or handled automatically via lookups, so they're not shown here
  const cin7Fields = [
    { value: 'CustomerName', label: 'Customer Name (Lookup)', required: true },
    { value: 'CustomerReference', label: 'Customer Reference (PO)', required: true },
    { value: 'SaleDate', label: 'Sale Date', required: true },
    { value: 'ShipBy', label: 'Required By / Due Date', required: false },
    { value: 'ShippingAddress', label: 'Ship To Address', required: false },
    { value: 'Currency', label: 'Currency', required: false },
    { value: 'TaxInclusive', label: 'Tax Inclusive', required: false },
    { value: 'SKU', label: 'Product SKU (Item Code)', required: true },
    { value: 'Quantity', label: 'Quantity (Cases)', required: false },
    { value: 'Total', label: 'Total', required: false },
    { value: 'Price', label: 'Price (or calculate from Total ÷ Cases)', required: false },
    { value: 'Discount', label: 'Discount', required: false },
    { value: 'Tax', label: 'Tax', required: false },
    { value: 'Notes', label: 'Notes', required: false },
    { value: 'AdditionalAttribute1', label: 'Additional Attribute 1 (Customer)', required: false }
  ];

  return (
    <div className="p-6 h-full flex gap-6 overflow-hidden">
      {/* Main Content Area */}
      <div className="flex-1 space-y-2 overflow-auto min-w-0">
        <div className="flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div>
            <h1 className="text-lg font-bold">Sales Order Uploader</h1>
            <p className="text-xs text-muted-foreground mt-1">
              {selectedClient
                ? `Upload CSV files for ${selectedClient.name}`
                : 'Select a client from the sidebar to begin'}
            </p>
          </div>
          {/* Process Step Indicator */}
          {selectedClientId && (
            <div className="flex items-center gap-3">
              {(() => {
                const steps = [
                  { id: 1, label: 'Upload', active: csvColumns.length === 0 },
                  { id: 2, label: 'Column Mapping', active: csvColumns.length > 0 && !validationResults },
                  { id: 3, label: 'Validation', active: validationResults && !processingResults },
                  { id: 4, label: 'Complete', active: processingResults }
                ];
                
                const currentStep = steps.find(s => s.active)?.id || 1;
                
                return steps.map((step, index) => {
                  const isCompleted = step.id < currentStep;
                  const isCurrent = step.id === currentStep;
                  const isUpcoming = step.id > currentStep;
                  
                  return (
                    <React.Fragment key={step.id}>
                      <div className="flex items-center gap-2">
                        <div className={`flex items-center justify-center w-7 h-7 transition-colors ${
                          isCompleted 
                            ? 'text-green-600' 
                            : isCurrent 
                            ? 'bg-blue-600 border-blue-600 text-white rounded-full border-2' 
                            : 'bg-white border-gray-300 text-gray-400 rounded-full border-2'
                        }`}>
                          {isCompleted ? (
                            <Check className="w-5 h-5" />
                          ) : (
                            <span className="text-xs font-semibold">{step.id}</span>
                          )}
                        </div>
                        <span className={`text-xs font-medium ${
                          isCurrent ? 'text-blue-600' : isCompleted ? 'text-gray-600' : 'text-gray-400'
                        }`}>
                          {step.label}
                        </span>
                      </div>
                      {index < steps.length - 1 && (
                        <div className={`h-px w-12 ${
                          isCompleted ? 'bg-green-600' : 'bg-gray-200'
                        }`} />
                      )}
                    </React.Fragment>
                  );
                });
              })()}
            </div>
          )}
        </div>
        {/* Reset Button - moved to top right */}
        {csvColumns.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={resetUpload}
          >
            <RotateCcw className="w-4 h-4 mr-2" />
            Reset
          </Button>
        )}
      </div>

      <div className="mt-8">
      {!selectedClientId && (
        <Card className="mt-6">
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              Please select a client from the sidebar to begin uploading sales orders.
            </p>
          </CardContent>
        </Card>
      )}

      {/* File Upload - Hide after upload */}
      {selectedClientId && csvColumns.length === 0 && !validationResults && (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => !uploading && document.getElementById('csv-upload').click()}
          className={cn(
            "border-2 border-dashed rounded-lg text-center transition-colors mt-6",
            isDragging ? "border-primary bg-primary/5" : "border-gray-300",
            uploading && "opacity-50 pointer-events-none",
            !uploading && "cursor-pointer hover:border-primary/50 hover:bg-primary/5"
          )}
        >
          <div className="p-8">
            {uploading ? (
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">Uploading...</p>
              </div>
            ) : (
              <>
                <Upload className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-sm font-medium mb-2">
                  Drag and drop a CSV file here, or click to browse
                </p>
                <p className="text-xs text-muted-foreground">
                  CSV files only
                </p>
                <Input
                  type="file"
                  accept=".csv"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileSelect(file);
                  }}
                  className="hidden"
                  id="csv-upload"
                />
              </>
            )}
          </div>
        </div>
      )}


        {/* Column Mapping Dialog */}
        <Dialog open={showMappingDialog} onOpenChange={setShowMappingDialog}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
            <DialogHeader className="pb-0">
              <DialogTitle>Column Mapping</DialogTitle>
              <DialogDescription>Map CSV columns to Cin7 fields</DialogDescription>
            </DialogHeader>
            <div className="flex-1 overflow-auto pr-2 -mt-2">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {templateAutoLoaded && (
                      <Badge variant="default" className="text-xs">Auto-loaded</Badge>
                    )}
                    {templateAutoLoaded && loadedTemplateName && (
                      <Badge variant="outline" className="text-xs">
                        {loadedTemplateName}
                      </Badge>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {mappingTemplates.length > 0 && (
                      <Select onValueChange={(value) => {
                        const template = mappingTemplates.find(t => t.id === value);
                        if (template) {
                          setColumnMapping(template.column_mapping);
                          toast.success(`Loaded template: ${template.name}`);
                        }
                      }}>
                        <SelectTrigger className="w-40">
                          <SelectValue placeholder="Load template" />
                        </SelectTrigger>
                        <SelectContent>
                          {mappingTemplates.map(template => (
                            <SelectItem key={template.id} value={template.id}>
                              {template.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    {!templateAutoLoaded && (
                      <Button size="sm" variant="outline" onClick={() => saveMapping(true)}>
                        Save as Template
                      </Button>
                    )}
                  </div>
                </div>
                <div className="border rounded-md">
                  <Table className="border-0">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Cin7 Field</TableHead>
                        <TableHead>CSV Column</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {cin7Fields.map(field => {
                        const hasQuantity = columnMapping['Quantity'] && columnMapping['Quantity'].trim() !== '';
                        const hasTotal = columnMapping['Total'] && columnMapping['Total'].trim() !== '';
                        const hasPrice = columnMapping['Price'] && columnMapping['Price'].trim() !== '';
                        const showCalculationNote = field.value === 'Price' && hasQuantity && hasTotal && !hasPrice;
                        
                        return (
                          <React.Fragment key={field.value}>
                            <TableRow>
                              <TableCell>
                                <div className="flex items-center gap-2">
                                  {field.label}
                                  {field.required && (
                                    <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-800 border-amber-300">Required</Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <Select
                                  value={(() => {
                                    const mappedValue = columnMapping[field.value];
                                    if (!mappedValue || String(mappedValue).trim() === '') {
                                      return undefined;
                                    }
                                    const trimmed = String(mappedValue).trim();
                                    return trimmed.length > 0 ? trimmed : undefined;
                                  })()}
                                  onValueChange={(value) => {
                                    const newMapping = {
                                      ...columnMapping,
                                      [field.value]: value === '__none__' ? '' : value
                                    };
                                    setColumnMapping(newMapping);
                                
                                // Debounced auto-save mapping when changed (if session exists)
                                // Clear any pending auto-save
                                if (autoSaveTimeoutRef.current) {
                                  clearTimeout(autoSaveTimeoutRef.current);
                                }
                                
                                // Only auto-save if not currently uploading or validating
                                if (sessionId && !uploading && !validating && !processing) {
                                  autoSaveTimeoutRef.current = setTimeout(async () => {
                                    try {
                                      await axios.post('/sales/mapping', {
                                        session_id: sessionId,
                                        column_mapping: newMapping
                                      });
                                    } catch (error) {
                                      // Silently fail - user can still validate and it will save then
                                      console.warn('Failed to auto-save mapping:', error);
                                    }
                                  }, 500); // 500ms debounce
                                }
                              }}
                            >
                              <SelectTrigger className="w-full border-0 text-xs h-8 [&>svg]:hidden justify-start !px-0 !py-0 [&>span[data-placeholder=true]]:!px-0 [&>span[data-placeholder=true]]:!py-0 [&>span[data-placeholder=true]]:!mr-0 [&>span[data-placeholder=true]]:!pr-0">
                                <SelectValue placeholder="Select column" className="[&[data-placeholder=true]]:!px-0 [&[data-placeholder=true]]:!py-0 [&[data-placeholder=true]]:!mr-0" />
                              </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none__" className="text-xs">-- None --</SelectItem>
                              {csvColumns
                                .filter(col => col != null && String(col).trim().length > 0)
                                .map(col => {
                                  const colStr = String(col).trim();
                                  return (
                                    <SelectItem key={colStr} value={colStr} className="text-xs">
                                      {colStr}
                                    </SelectItem>
                                  );
                                })}
                            </SelectContent>
                          </Select>
                        </TableCell>
                      </TableRow>
                      {showCalculationNote && (
                        <TableRow>
                          <TableCell colSpan={2} className="text-xs text-muted-foreground italic pl-12">
                            Price will be calculated from {columnMapping['Total']} ÷ {columnMapping['Quantity']} if Price is not mapped
                          </TableCell>
                        </TableRow>
                      )}
                      {field.value === 'Price' && !hasPrice && (
                        <TableRow>
                          <TableCell colSpan={2} className="text-xs text-muted-foreground pl-12">
                            Optional: Map directly or leave empty to calculate from Total ÷ Quantity (Cases)
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                    );
                  })}
                  </TableBody>
                </Table>
                </div>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        {/* Validation Results */}
        {validationResults && (
          <div className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-bold">Validation Results</h2>
              {/* Column Mapping - moved to top right of table */}
              {csvColumns.length > 0 && (
                <div className="flex items-center gap-2">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="border-0"
                    onClick={() => setShowMappingDialog(true)}
                  >
                    <Map className="w-4 h-4 mr-2" />
                    Column Mapping
                  </Button>
                  {templateAutoLoaded && (
                    <Badge variant="default" className="text-xs">Auto-loaded</Badge>
                  )}
                  {templateAutoLoaded && loadedTemplateName && (
                    <Badge variant="outline" className="text-xs">
                      {loadedTemplateName}
                    </Badge>
                  )}
                </div>
              )}
            </div>
            <div className="border rounded-md">
                  <Table className="border-0">
                    <TableHeader>
                      <TableRow className="h-8">
                        <TableHead className="py-1 text-xs font-semibold">PO #</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Customer</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Order Date</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Due Date</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Lines</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Cases</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Total</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Status</TableHead>
                        <TableHead className="py-1 text-xs font-semibold">Errors</TableHead>
                        <TableHead className="py-1 text-xs font-semibold"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {validationResults.invalidRows.map((row) => (
                        <React.Fragment key={row.row_number}>
                          <TableRow className="h-8">
                            <TableCell className="text-xs py-1">
                              {row.po_number || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.customer_name || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.order_date || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.due_date || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.line_item_count || 0}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.total_cases ? row.total_cases.toFixed(2) : '0.00'}
                            </TableCell>
                            <TableCell className="text-xs font-medium py-1">
                              {row.order_total ? `$${row.order_total.toFixed(2)}` : '$0.00'}
                            </TableCell>
                            <TableCell className="py-1">
                              <Badge variant="destructive" className="text-xs h-5 px-1.5">
                                <XCircle className="h-2.5 w-2.5 mr-0.5" />
                                Invalid
                              </Badge>
                            </TableCell>
                            <TableCell className="py-1">
                              <div className="space-y-0.5">
                                {row.errors?.map((error, eIdx) => (
                                  <div key={eIdx} className="text-xs text-destructive leading-tight">
                                    {error}
                                  </div>
                                ))}
                              </div>
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => toggleRowExpansion(row.row_number)}
                                >
                                  {expandedRows.has(row.row_number) ? 'Hide' : 'Show'}
                                </Button>
                                {isAdmin && row.preview_payload && (
                                  <>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="h-6 w-6 p-0"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setOpenPayloadModal(row.row_number);
                                      }}
                                    >
                                      <Code2 className="h-3.5 w-3.5" />
                                    </Button>
                                    <Dialog open={openPayloadModal === row.row_number} onOpenChange={(open) => {
                                      if (!open) setOpenPayloadModal(null);
                                    }}>
                                      <DialogContent className="max-w-6xl max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
                                        <DialogHeader>
                                          <DialogTitle>Cin7 API Payload</DialogTitle>
                                        </DialogHeader>
                                        <div className="space-y-4">
                                          {row.preview_payload?.error ? (
                                            <div className="border rounded-md overflow-hidden bg-red-50 p-4">
                                              <p className="text-sm text-red-800">{row.preview_payload.error}</p>
                                            </div>
                                          ) : (
                                            <>
                                              {row.preview_payload?.customer_creation && (
                                                <div className="mb-4">
                                                  <h6 className="text-sm font-semibold mb-2 text-blue-700">Customer Creation Payload (Before Step 1)</h6>
                                                  <div className="border rounded-md overflow-hidden bg-blue-50">
                                                    <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                      <code>{JSON.stringify(row.preview_payload.customer_creation, null, 2)}</code>
                                                    </pre>
                                    <p className="p-2 text-xs text-blue-700 bg-blue-100">
                                      This customer will be created first. The Sale payload will reference the CustomerID returned from the customer creation, along with the Customer name.
                                    </p>
                                                  </div>
                                                </div>
                                              )}
                                              {row.preview_payload?.sale && (
                                                <div>
                                                  <h6 className="text-sm font-semibold mb-2 text-gray-700">Sale Payload (Step 1)</h6>
                                                  <div className="border rounded-md overflow-hidden bg-gray-50">
                                                    <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                      <code>{JSON.stringify(row.preview_payload.sale, null, 2)}</code>
                                                    </pre>
                                                  </div>
                                                </div>
                                              )}
                                              {row.preview_payload?.sale_order && (
                                                <div>
                                                  <h6 className="text-sm font-semibold mb-2 text-gray-700">Sale Order Payload (Step 2)</h6>
                                                  <div className="border rounded-md overflow-hidden bg-gray-50">
                                                    <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                      <code>{JSON.stringify(row.preview_payload.sale_order, null, 2)}</code>
                                                    </pre>
                                                  </div>
                                                </div>
                                              )}
                                              {!row.preview_payload?.sale && !row.preview_payload?.sale_order && (
                                                <div className="border rounded-md overflow-hidden bg-gray-50">
                                                  <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                    <code>{JSON.stringify(row.preview_payload, null, 2)}</code>
                                                  </pre>
                                                </div>
                                              )}
                                            </>
                                          )}
                                          <div className="text-xs text-muted-foreground">
                                            {row.preview_payload?.sale || row.preview_payload?.sale_order
                                              ? 'These are the JSON payloads that will be sent to Cin7 API. First the Sale is created, then the Sale Order is created with the Sale ID.'
                                              : 'This is the JSON payload that will be sent to Cin7 API when creating this sales order.'}
                                          </div>
                                        </div>
                                      </DialogContent>
                                    </Dialog>
                                  </>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                          {expandedRows.has(row.row_number) && (
                            <TableRow>
                              <TableCell colSpan={10} className="bg-gray-50/50 p-3">
                                <div className="space-y-3">
                                  {renderJsonPayload(row)}
                                  {renderPreparedData(row)}
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </React.Fragment>
                      ))}
                      {validationResults.validRows?.map((row) => (
                        <React.Fragment key={row.row_number}>
                          <TableRow className="h-8">
                            <TableCell className="text-xs py-1">
                              {row.po_number || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.customer_name || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.order_date || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.due_date || '-'}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.line_item_count || 0}
                            </TableCell>
                            <TableCell className="text-xs py-1">
                              {row.total_cases ? row.total_cases.toFixed(2) : '0.00'}
                            </TableCell>
                            <TableCell className="text-xs font-medium py-1">
                              {row.order_total ? `$${row.order_total.toFixed(2)}` : '$0.00'}
                            </TableCell>
                            <TableCell className="py-1">
                              <Badge variant="default" className="bg-green-600 text-xs h-5 px-1.5">
                                <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />
                                Valid
                              </Badge>
                            </TableCell>
                            <TableCell className="py-1">
                              <span className="text-xs text-muted-foreground">No errors</span>
                            </TableCell>
                            <TableCell className="py-1">
                              <div className="flex items-center gap-2">
                                <button
                                  className="text-xs text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                                  onClick={() => toggleRowExpansion(row.row_number)}
                                >
                                  {expandedRows.has(row.row_number) ? 'Hide' : 'Show'}
                                </button>
                                {isAdmin && row.preview_payload && (
                                  <>
                                    <button
                                      className="text-xs text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setOpenPayloadModal(row.row_number);
                                      }}
                                    >
                                      <Code2 className="h-3.5 w-3.5 inline" />
                                    </button>
                                    <Dialog open={openPayloadModal === row.row_number} onOpenChange={(open) => {
                                      if (!open) setOpenPayloadModal(null);
                                    }}>
                                      <DialogContent className="max-w-6xl max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
                                        <DialogHeader>
                                          <DialogTitle>Cin7 API Payload</DialogTitle>
                                        </DialogHeader>
                                        <div className="space-y-4">
                                          {row.preview_payload?.error ? (
                                            <div className="border rounded-md overflow-hidden bg-red-50 p-4">
                                              <p className="text-sm text-red-800">{row.preview_payload.error}</p>
                                            </div>
                                          ) : (
                                            <>
                                              {row.preview_payload?.customer_creation && (
                                                <div className="mb-4">
                                                  <h6 className="text-sm font-semibold mb-2 text-blue-700">Customer Creation Payload (Before Step 1)</h6>
                                                  <div className="border rounded-md overflow-hidden bg-blue-50">
                                                    <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                      <code>{JSON.stringify(row.preview_payload.customer_creation, null, 2)}</code>
                                                    </pre>
                                    <p className="p-2 text-xs text-blue-700 bg-blue-100">
                                      This customer will be created first. The Sale payload will reference the CustomerID returned from the customer creation, along with the Customer name.
                                    </p>
                                                  </div>
                                                </div>
                                              )}
                                              {row.preview_payload?.sale && (
                                                <div>
                                                  <h6 className="text-sm font-semibold mb-2 text-gray-700">Sale Payload (Step 1)</h6>
                                                  <div className="border rounded-md overflow-hidden bg-gray-50">
                                                    <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                      <code>{JSON.stringify(row.preview_payload.sale, null, 2)}</code>
                                                    </pre>
                                                  </div>
                                                </div>
                                              )}
                                              {row.preview_payload?.sale_order && (
                                                <div>
                                                  <h6 className="text-sm font-semibold mb-2 text-gray-700">Sale Order Payload (Step 2)</h6>
                                                  <div className="border rounded-md overflow-hidden bg-gray-50">
                                                    <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                      <code>{JSON.stringify(row.preview_payload.sale_order, null, 2)}</code>
                                                    </pre>
                                                  </div>
                                                </div>
                                              )}
                                              {!row.preview_payload?.sale && !row.preview_payload?.sale_order && (
                                                <div className="border rounded-md overflow-hidden bg-gray-50">
                                                  <pre className="p-4 text-xs font-mono overflow-auto max-h-96 bg-white">
                                                    <code>{JSON.stringify(row.preview_payload, null, 2)}</code>
                                                  </pre>
                                                </div>
                                              )}
                                            </>
                                          )}
                                          <div className="text-xs text-muted-foreground">
                                            {row.preview_payload?.sale || row.preview_payload?.sale_order
                                              ? 'These are the JSON payloads that will be sent to Cin7 API. First the Sale is created, then the Sale Order is created with the Sale ID.'
                                              : 'This is the JSON payload that will be sent to Cin7 API when creating this sales order.'}
                                          </div>
                                        </div>
                                      </DialogContent>
                                    </Dialog>
                                  </>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                          {expandedRows.has(row.row_number) && (
                            <TableRow>
                              <TableCell colSpan={10} className="bg-gray-50/50 p-3">
                                <div className="space-y-5">
                                  {renderJsonPayload(row)}
                                  {renderPreparedData(row)}
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </React.Fragment>
                      ))}
                    </TableBody>
                    <tfoot>
                      <TableRow>
                        <TableCell colSpan={10} className="border-t bg-gray-50/50 py-2">
                          <div className="text-xs text-muted-foreground">
                            Valid: <span className="font-semibold text-black">{validationResults.validCount}</span> Invalid: <span className="font-semibold text-red-600">{validationResults.invalidCount}</span>
                          </div>
                        </TableCell>
                      </TableRow>
                    </tfoot>
                  </Table>
            </div>

            <div className="flex gap-2 mt-4">
              <Button
                onClick={createSalesOrders}
                disabled={validationResults.invalidCount > 0 || processing}
              >
                {processing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2" />
                    Create Sales Orders
                  </>
                )}
              </Button>
            </div>
          </div>
        )}

        {/* Processing Results */}
        {processingResults && (
            <Card className="mt-6">
              <CardHeader>
                <CardTitle className="text-sm">Processing Results</CardTitle>
                <CardDescription className="text-xs">
                  {processingResults.successful} successful, {processingResults.failed} failed
                </CardDescription>
              </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <Badge variant="default">{processingResults.successful} Successful</Badge>
                {processingResults.failed > 0 && (
                  <Badge variant="destructive">{processingResults.failed} Failed</Badge>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Uploaded Data Table */}
        {csvRows.length > 0 && csvColumns.length > 0 && !validationResults && (() => {
          // Get only columns that are mapped
          const mappedColumns = Object.values(columnMapping).filter(col => col && col.trim());
          const columnsToShow = mappedColumns.length > 0 ? mappedColumns : csvColumns;
          
          return (
            <div className="border rounded-md mt-6">
              <Table className="border-0">
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs w-16">Row</TableHead>
                    {columnsToShow.map((col) => (
                      <TableHead key={col} className="text-xs">
                        {col}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {csvRows.slice(0, 50).map((row, idx) => {
                    const rowData = row.data || row;
                    return (
                      <TableRow key={idx}>
                        <TableCell className="font-medium text-xs">{row.row_number || idx + 1}</TableCell>
                        {columnsToShow.map((col) => (
                          <TableCell key={col} className="text-xs">
                            {rowData[col] || '-'}
                          </TableCell>
                        ))}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              {csvRows.length > 50 && (
                <div className="p-4 text-center text-xs text-muted-foreground border-t">
                  Showing first 50 of {csvRows.length} rows
                </div>
              )}
            </div>
          );
        })()}

        {/* Action Buttons */}
        {csvColumns.length > 0 && !validationResults && (
          <div className="flex gap-2 mt-6">
            <Button
              onClick={refreshCache}
              disabled={refreshingCache || !connected}
              variant="outline"
              title="Refresh customer and product cache from Cin7"
            >
              {refreshingCache ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Refreshing...
                </>
              ) : (
                <>
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Refresh Cache
                </>
              )}
            </Button>
            <Button
              onClick={validateData}
              disabled={validating || !connected}
              className="flex-1"
            >
              {validating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Validating...
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Validate Data
                </>
              )}
            </Button>
          </div>
        )}
      </div>
      </div>
    </div>
  );
};

export default SalesOrderUploader;



