import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { CheckCircle2, XCircle, AlertCircle, RefreshCw, Download, Code2 } from 'lucide-react';
import { useClient } from '../contexts/ClientContext';

const DataValidation = ({ sessionId, onValidationComplete }) => {
  const { selectedClientId } = useClient();
  const [validating, setValidating] = useState(false);
  const [validationResults, setValidationResults] = useState(null);
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [showPayloadRows, setShowPayloadRows] = useState(new Set());

  const validateData = async () => {
    if (!sessionId) {
      toast.error('Please upload a CSV file first');
      return;
    }

    if (!selectedClientId) {
      toast.error('Please select a client');
      return;
    }

    setValidating(true);
    toast.info('Fetching latest customers and products from Cin7...', { duration: 3000 });

    try {
      const response = await axios.post('/sales/validate', { session_id: sessionId });

      const results = {
        validCount: response.data.valid_count,
        invalidCount: response.data.invalid_count,
        validRows: response.data.valid_rows || [],
        invalidRows: response.data.invalid_rows || [],
        customerCount: response.data.customer_count,
        productCount: response.data.product_count
      };

      // Debug: log first row to check field_status
      if (results.invalidRows.length > 0) {
        console.log('First invalid row:', results.invalidRows[0]);
        console.log('Has field_status?', !!results.invalidRows[0]?.field_status);
        console.log('Has mapped_data?', !!results.invalidRows[0]?.mapped_data);
      }

      setValidationResults(results);

      if (results.invalidCount > 0) {
        toast.warning(`${results.invalidCount} rows have errors`);
      } else {
        toast.success('All rows validated successfully');
      }

      if (onValidationComplete) {
        onValidationComplete(results);
      }
    } catch (error) {
      toast.error(error.response?.data?.error || 'Validation failed');
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

  const renderRowData = (row) => {
    if (!row || !row.data) return null;

    return (
      <div className="space-y-1 text-xs">
        {Object.entries(row.data).map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <span className="font-medium text-muted-foreground w-32 truncate">{key}:</span>
            <span className="flex-1">{String(value || '-')}</span>
          </div>
        ))}
      </div>
    );
  };

  const renderPreparedData = (row) => {
    if (!row) return null;

    // Build field status from mapped_data if field_status isn't available
    let fieldStatus = row.field_status || {};
    const mappedData = row.mapped_data || {};
    
    // If field_status is missing, build it from mapped_data
    if (!row.field_status && row.mapped_data) {
      const requiredFields = ['CustomerName', 'CustomerReference', 'SaleDate', 'SKU', 'Price'];
      const optionalFields = ['Currency', 'TaxInclusive', 'ProductName', 'Quantity', 'Discount', 'Tax', 'Notes'];
      
      // Build basic status from mapped_data
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

    // Ensure we have some field status to show
    if (Object.keys(fieldStatus).length === 0) {
      console.warn('No field status available for row', row.row_number);
      return (
        <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-md">
          <p className="text-sm text-yellow-800">
            Field status data not available. Please check backend response.
          </p>
        </div>
      );
    }

    return (
      <div className="mt-4">
        <h5 className="text-sm font-semibold mb-2">Prepared Data for Cin7</h5>
        <div className="border rounded-md overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-48">Cin7 Field</TableHead>
                <TableHead className="w-32">Status</TableHead>
                <TableHead>Value</TableHead>
                <TableHead className="w-40">Source</TableHead>
                <TableHead>Message</TableHead>
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
                  <TableRow key={field.key}>
                    <TableCell className="font-medium">
                      {field.label}
                      {field.required && <span className="text-destructive ml-1">*</span>}
                    </TableCell>
                    <TableCell>
                      <span className={`text-xs font-medium ${statusTextColors[status.status] || statusTextColors.optional}`}>
                        {status.status === 'ready' ? 'Ready' : 
                         status.status === 'missing' ? 'Missing' :
                         status.status === 'invalid' ? 'Invalid' : 'Optional'}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <div className="truncate text-sm">
                        {status.value ? String(status.value) : <span className="text-muted-foreground">-</span>}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {status.source || '-'}
                    </TableCell>
                    <TableCell className={`text-xs ${status.status === 'invalid' ? 'text-red-600' : 'text-muted-foreground'}`}>
                      {status.message || '-'}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </div>
    );
  };

  const renderErrors = (errors) => {
    if (!errors || errors.length === 0) return null;

    return (
      <div className="space-y-1">
        {errors.map((error, idx) => (
          <div key={idx} className="text-xs text-destructive flex items-start gap-2">
            <XCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        ))}
      </div>
    );
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
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Code2 className="h-4 w-4" />
            <h5 className="text-sm font-semibold">Cin7 API Payloads (Preview)</h5>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setShowPayloadRows(prev => {
                const next = new Set(prev);
                if (next.has(row.row_number)) {
                  next.delete(row.row_number);
                } else {
                  next.add(row.row_number);
                }
                return next;
              });
            }}
          >
            {isVisible ? 'Hide' : 'Show'} Payloads
          </Button>
        </div>
        {isVisible && (
          <>
            {hasError ? (
              <div className="border rounded-md overflow-hidden bg-red-50 p-4">
                <p className="text-sm text-red-800">{payloads.error}</p>
              </div>
            ) : (
              <>
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
              These are the JSON payloads that will be sent to Cin7 API. First the Sale is created, then the Sale Order is created with the Sale ID.
            </div>
          </>
        )}
      </div>
    );
  };

  if (!sessionId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Data Validation</CardTitle>
          <CardDescription>Upload a CSV file to begin validation</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Data Validation</CardTitle>
              <CardDescription>
                Validate CSV data against Cin7 API before creating sales orders
              </CardDescription>
            </div>
            <Button onClick={validateData} disabled={validating}>
              {validating ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Validating...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Validate Data
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {validationResults ? (
            <div className="space-y-4">
              <div className="flex gap-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                  <span className="font-medium">{validationResults.validCount}</span>
                  <span className="text-sm text-muted-foreground">Valid rows</span>
                </div>
                <div className="flex items-center gap-2">
                  <XCircle className="h-5 w-5 text-red-600" />
                  <span className="font-medium">{validationResults.invalidCount}</span>
                  <span className="text-sm text-muted-foreground">Invalid rows</span>
                </div>
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-5 w-5 text-blue-600" />
                  <span className="font-medium">
                    {validationResults.validCount + validationResults.invalidCount}
                  </span>
                  <span className="text-sm text-muted-foreground">Total rows</span>
                </div>
                {validationResults.customerCount !== undefined && (
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {validationResults.customerCount} customers loaded
                    </Badge>
                  </div>
                )}
                {validationResults.productCount !== undefined && (
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {validationResults.productCount} products loaded
                    </Badge>
                  </div>
                )}
              </div>

              <Tabs defaultValue="all" className="w-full">
                <TabsList>
                  <TabsTrigger value="all">
                    All ({validationResults.validCount + validationResults.invalidCount})
                  </TabsTrigger>
                  <TabsTrigger value="valid">
                    Valid ({validationResults.validCount})
                  </TabsTrigger>
                  <TabsTrigger value="invalid">
                    Invalid ({validationResults.invalidCount})
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="all" className="space-y-4">
                  <div className="space-y-2">
                    {validationResults.validRows.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold mb-2 text-green-600">
                          Valid Rows
                        </h4>
                        <div className="border rounded-md">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-20">Row</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Data Preview</TableHead>
                                <TableHead className="w-20"></TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {validationResults.validRows.map((row) => (
                                <React.Fragment key={row.row_number}>
                                  <TableRow>
                                    <TableCell className="font-medium">
                                      {row.row_number}
                                    </TableCell>
                                    <TableCell>
                                      <Badge variant="default" className="bg-green-600">
                                        <CheckCircle2 className="h-3 w-3 mr-1" />
                                        Valid
                                      </Badge>
                                    </TableCell>
                                    <TableCell>
                                      <div className="text-xs text-muted-foreground max-w-md truncate">
                                        {JSON.stringify(row.data).substring(0, 100)}...
                                      </div>
                                    </TableCell>
                                    <TableCell>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => toggleRowExpansion(row.row_number)}
                                      >
                                        {expandedRows.has(row.row_number) ? 'Hide' : 'Show'}
                                      </Button>
                                    </TableCell>
                                  </TableRow>
                                  {expandedRows.has(row.row_number) && (
                                    <TableRow>
                                      <TableCell colSpan={4} className="bg-muted/50 p-4">
                                        <div className="space-y-4">
                                          {renderJsonPayload(row)}
                                          {renderPreparedData(row)}
                                          <div>
                                            <h5 className="text-sm font-semibold mb-2">Raw CSV Data</h5>
                                            {renderRowData(row)}
                                          </div>
                                        </div>
                                      </TableCell>
                                    </TableRow>
                                  )}
                                </React.Fragment>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}

                    {validationResults.invalidRows.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold mb-2 text-red-600">
                          Invalid Rows
                        </h4>
                        <div className="border rounded-md">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-20">Row</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Errors</TableHead>
                                <TableHead className="w-20"></TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {validationResults.invalidRows.map((row) => (
                                <React.Fragment key={row.row_number}>
                                  <TableRow>
                                    <TableCell className="font-medium">
                                      {row.row_number}
                                    </TableCell>
                                    <TableCell>
                                      <Badge variant="destructive">
                                        <XCircle className="h-3 w-3 mr-1" />
                                        Invalid
                                      </Badge>
                                    </TableCell>
                                    <TableCell>
                                      {renderErrors(row.errors)}
                                    </TableCell>
                                    <TableCell>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => toggleRowExpansion(row.row_number)}
                                      >
                                        {expandedRows.has(row.row_number) ? 'Hide' : 'Show'}
                                      </Button>
                                    </TableCell>
                                  </TableRow>
                                  {expandedRows.has(row.row_number) && (
                                    <TableRow>
                                      <TableCell colSpan={4} className="bg-muted/50 p-4">
                                        <div className="space-y-4">
                                          {renderPreparedData(row) || (
                                            <div className="text-sm text-muted-foreground">
                                              Field status data not available. Showing mapped data only.
                                            </div>
                                          )}
                                          {renderPreparedData(row) && (
                                            <div>
                                              <h5 className="text-sm font-semibold mb-2 mt-4">Raw CSV Data</h5>
                                              {renderRowData(row)}
                                            </div>
                                          )}
                                          {!renderPreparedData(row) && renderRowData(row)}
                                        </div>
                                      </TableCell>
                                    </TableRow>
                                  )}
                                </React.Fragment>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="valid" className="space-y-4">
                  {validationResults.validRows.length > 0 ? (
                    <div className="border rounded-md">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-20">Row</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Data Preview</TableHead>
                            <TableHead className="w-20"></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {validationResults.validRows.map((row) => (
                            <React.Fragment key={row.row_number}>
                              <TableRow>
                                <TableCell className="font-medium">
                                  {row.row_number}
                                </TableCell>
                                <TableCell>
                                  <Badge variant="default" className="bg-green-600">
                                    <CheckCircle2 className="h-3 w-3 mr-1" />
                                    Valid
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  <div className="text-xs text-muted-foreground max-w-md truncate">
                                    {JSON.stringify(row.data).substring(0, 100)}...
                                  </div>
                                </TableCell>
                                <TableCell>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => toggleRowExpansion(row.row_number)}
                                  >
                                    {expandedRows.has(row.row_number) ? 'Hide' : 'Show'}
                                  </Button>
                                </TableCell>
                              </TableRow>
                              {expandedRows.has(row.row_number) && (
                                <TableRow>
                                  <TableCell colSpan={4} className="bg-muted/50 p-4">
                                    <div className="space-y-4">
                                      {renderPreparedData(row)}
                                      <div>
                                        <h5 className="text-sm font-semibold mb-2">Raw CSV Data</h5>
                                        {renderRowData(row)}
                                      </div>
                                    </div>
                                  </TableCell>
                                </TableRow>
                              )}
                            </React.Fragment>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No valid rows
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="invalid" className="space-y-4">
                  {validationResults.invalidRows.length > 0 ? (
                    <div className="border rounded-md">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-20">Row</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Errors</TableHead>
                            <TableHead className="w-20"></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {validationResults.invalidRows.map((row) => (
                            <React.Fragment key={row.row_number}>
                              <TableRow>
                                <TableCell className="font-medium">
                                  {row.row_number}
                                </TableCell>
                                <TableCell>
                                  <Badge variant="destructive">
                                    <XCircle className="h-3 w-3 mr-1" />
                                    Invalid
                                  </Badge>
                                </TableCell>
                                    <TableCell>
                                      {renderErrors(row.errors)}
                                    </TableCell>
                                    <TableCell>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => toggleRowExpansion(row.row_number)}
                                      >
                                        {expandedRows.has(row.row_number) ? 'Hide' : 'Show'}
                                      </Button>
                                    </TableCell>
                                  </TableRow>
                                  {expandedRows.has(row.row_number) && (
                                    <TableRow>
                                      <TableCell colSpan={4} className="bg-muted/50 p-4">
                                        <div className="space-y-4">
                                          {renderPreparedData(row) || (
                                            <div className="text-sm text-muted-foreground">
                                              Field status data not available. Showing mapped data only.
                                            </div>
                                          )}
                                          {renderPreparedData(row) && (
                                            <div>
                                              <h5 className="text-sm font-semibold mb-2 mt-4">Raw CSV Data</h5>
                                              {renderRowData(row)}
                                            </div>
                                          )}
                                          {!renderPreparedData(row) && renderRowData(row)}
                                        </div>
                                      </TableCell>
                                    </TableRow>
                                  )}
                            </React.Fragment>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No invalid rows
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Click "Validate Data" to validate the uploaded CSV file
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default DataValidation;



