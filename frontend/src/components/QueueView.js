import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { ChevronDown, ChevronRight, RefreshCw, CheckCircle2, XCircle, Clock, FileText } from 'lucide-react';
import { cn } from '../lib/utils';

const QueueView = () => {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedUploads, setExpandedUploads] = useState(new Set());
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterClient, setFilterClient] = useState('all');

  const loadQueue = async () => {
    try {
      setLoading(true);
      const params = {};
      if (filterStatus !== 'all') {
        params.status = filterStatus;
      }
      if (filterClient !== 'all') {
        params.client_id = filterClient;
      }
      
      const response = await axios.get('/webhooks/queue', { params });
      setUploads(response.data.uploads || []);
    } catch (error) {
      console.error('Failed to load queue:', error);
      toast.error('Failed to load queue');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
    // Refresh every 30 seconds
    const interval = setInterval(loadQueue, 30000);
    return () => clearInterval(interval);
  }, [filterStatus, filterClient]);

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
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Upload Queue</h1>
          <p className="text-muted-foreground mt-1">
            View order processing results from email webhooks
          </p>
        </div>
        <Button onClick={loadQueue} disabled={loading} variant="outline">
          <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <div>
              <label className="text-sm font-medium mb-1 block">Status</label>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="px-3 py-2 border rounded-md"
              >
                <option value="all">All</option>
                <option value="processing">Processing</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Client</label>
              <select
                value={filterClient}
                onChange={(e) => setFilterClient(e.target.value)}
                className="px-3 py-2 border rounded-md"
              >
                <option value="all">All Clients</option>
                {Array.from(new Set(uploads.map(u => u.client_id).filter(Boolean))).map(clientId => {
                  const upload = uploads.find(u => u.client_id === clientId);
                  return (
                    <option key={clientId} value={clientId}>
                      {upload?.client_name || clientId}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Uploads Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Uploads</CardTitle>
        </CardHeader>
        <CardContent>
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
                  <TableHead>Client</TableHead>
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
                          </div>
                        </TableCell>
                        <TableCell>{upload.client_name || 'N/A'}</TableCell>
                        <TableCell>{formatDate(upload.created_at)}</TableCell>
                        <TableCell>{getStatusBadge(upload.status)}</TableCell>
                        <TableCell className="text-right">{upload.order_results?.length || 0}</TableCell>
                        <TableCell className="text-right text-green-600">{upload.successful_orders || 0}</TableCell>
                        <TableCell className="text-right text-red-600">{upload.failed_orders || 0}</TableCell>
                      </TableRow>
                      {isExpanded && (
                        <TableRow>
                          <TableCell colSpan={8} className="bg-muted/30 p-0">
                            <div className="p-4 space-y-4">
                              {/* Successful Orders */}
                              {successfulOrders.length > 0 && (
                                <div>
                                  <h4 className="font-semibold mb-2 flex items-center gap-2 text-green-600">
                                    <CheckCircle2 className="h-4 w-4" />
                                    Successful Orders ({successfulOrders.length})
                                  </h4>
                                  <div className="space-y-2">
                                    {successfulOrders.map((order) => (
                                      <Card key={order.id} className="bg-green-50 border-green-200">
                                        <CardContent className="p-3">
                                          <div className="grid grid-cols-4 gap-4 text-sm">
                                            <div>
                                              <span className="text-muted-foreground">Order:</span>
                                              <div className="font-medium">{order.order_key}</div>
                                            </div>
                                            <div>
                                              <span className="text-muted-foreground">Customer:</span>
                                              <div className="font-medium">{order.order_data?.customer_name || 'N/A'}</div>
                                            </div>
                                            <div>
                                              <span className="text-muted-foreground">PO #:</span>
                                              <div className="font-medium">{order.order_data?.po_number || 'N/A'}</div>
                                            </div>
                                            <div>
                                              <span className="text-muted-foreground">Sale Order ID:</span>
                                              <div className="font-medium font-mono text-xs">{order.sale_order_id || 'N/A'}</div>
                                            </div>
                                          </div>
                                        </CardContent>
                                      </Card>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {/* Failed Orders */}
                              {failedOrders.length > 0 && (
                                <div>
                                  <h4 className="font-semibold mb-2 flex items-center gap-2 text-red-600">
                                    <XCircle className="h-4 w-4" />
                                    Failed Orders ({failedOrders.length})
                                  </h4>
                                  <div className="space-y-2">
                                    {failedOrders.map((order) => (
                                      <Card key={order.id} className="bg-red-50 border-red-200">
                                        <CardContent className="p-3">
                                          <div className="grid grid-cols-4 gap-4 text-sm mb-2">
                                            <div>
                                              <span className="text-muted-foreground">Order:</span>
                                              <div className="font-medium">{order.order_key}</div>
                                            </div>
                                            <div>
                                              <span className="text-muted-foreground">Customer:</span>
                                              <div className="font-medium">{order.order_data?.customer_name || 'N/A'}</div>
                                            </div>
                                            <div>
                                              <span className="text-muted-foreground">PO #:</span>
                                              <div className="font-medium">{order.order_data?.po_number || 'N/A'}</div>
                                            </div>
                                            <div>
                                              <span className="text-muted-foreground">Status:</span>
                                              <div className="font-medium">
                                                {order.status === 'processing' ? (
                                                  <Badge variant="secondary" className="bg-blue-500">
                                                    <Clock className="h-3 w-3 mr-1" />
                                                    Processing
                                                  </Badge>
                                                ) : (
                                                  <Badge variant="destructive">Failed</Badge>
                                                )}
                                              </div>
                                            </div>
                                          </div>
                                          {order.error_message && (
                                            <div className="mt-2 p-2 bg-red-100 rounded text-xs text-red-800 font-mono">
                                              {order.error_message}
                                            </div>
                                          )}
                                        </CardContent>
                                      </Card>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {successfulOrders.length === 0 && failedOrders.length === 0 && (
                                <div className="text-center py-4 text-muted-foreground">
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
        </CardContent>
      </Card>
    </div>
  );
};

export default QueueView;

