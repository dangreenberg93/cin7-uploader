import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';
import { Plus, Trash2, Edit, Users, Building2, Key, Settings as SettingsIcon, Search, X, Save, StarOff, AlertCircle, Workflow, FileText, RefreshCw, Copy, Cloud, Terminal } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { useClient } from '../contexts/ClientContext';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from './ui/alert-dialog';

const Admin = ({ user }) => {
  const { clients: activeClients, allClients, refreshClients } = useClient(); // allClients for table, activeClients for selectors
  const [loading, setLoading] = useState(false);
  const [showCreateClient, setShowCreateClient] = useState(false);
  const [newClientName, setNewClientName] = useState('');
  const [selectedClientForEdit, setSelectedClientForEdit] = useState(null);
  const [clientUsers, setClientUsers] = useState([]);
  const [credentials, setCredentials] = useState(null);
  const [clientSettings, setClientSettings] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [clientToDelete, setClientToDelete] = useState(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionTestResult, setConnectionTestResult] = useState(null);
  const [showAddUserDialog, setShowAddUserDialog] = useState(false);
  const [userSearchQuery, setUserSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchingUsers, setSearchingUsers] = useState(false);
  const [selectedRole, setSelectedRole] = useState('user');
  const [allUsers, setAllUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [mappingTemplates, setMappingTemplates] = useState([]);
  const [loadingMappings, setLoadingMappings] = useState(false);
  const [editingMapping, setEditingMapping] = useState(null);
  const [showMappingDialog, setShowMappingDialog] = useState(false);
  const [mappingName, setMappingName] = useState('');
  const [columnMapping, setColumnMapping] = useState({});
  const [isDefault, setIsDefault] = useState(false);
  const [csvColumns, setCsvColumns] = useState([]);
  const [saleType, setSaleType] = useState('');
  const [taxRule, setTaxRule] = useState('');
  const [defaultStatus, setDefaultStatus] = useState('DRAFT');
  const [workflowData, setWorkflowData] = useState(null);
  const [loadingWorkflow, setLoadingWorkflow] = useState(false);
  const [clientStatusFilter, setClientStatusFilter] = useState('active'); // 'active', 'inactive'
  const [envFileContent, setEnvFileContent] = useState('');
  const [serviceName, setServiceName] = useState('cin7-uploader');
  const [region, setRegion] = useState('us-central1');
  const [savingConfig, setSavingConfig] = useState(false);
  const [loadingConfig, setLoadingConfig] = useState(false);

  useEffect(() => {
    if (selectedClientForEdit) {
      loadClientDetails();
    }
  }, [selectedClientForEdit]);

  useEffect(() => {
    loadAllUsers();
  }, [allClients]); // Reload when clients change

  useEffect(() => {
    loadDeploymentConfig();
  }, []); // Load on mount

  const loadClientDetails = async () => {
    if (!selectedClientForEdit) return;

    try {
      const [usersRes, credsRes, settingsRes, mappingsRes] = await Promise.all([
        axios.get(`/admin/clients/${selectedClientForEdit}/users`).catch(() => ({ data: [] })),
        axios.get(`/credentials/clients/${selectedClientForEdit}`).catch(() => ({ data: null })),
        axios.get(`/settings/clients/${selectedClientForEdit}`).catch(() => ({ data: null })),
        axios.get(`/mappings/clients/${selectedClientForEdit}`).catch(() => ({ data: [] }))
      ]);

      setClientUsers(usersRes.data || []);
      setCredentials(credsRes.data || null);
      setClientSettings(settingsRes.data || null);
      setMappingTemplates(mappingsRes.data || []);
      setConnectionTestResult(null); // Clear test result when switching clients
      
      // Set sale_type, tax_rule, default_status from credentials
      if (credsRes.data) {
        setSaleType(credsRes.data.sale_type || '');
        setTaxRule(credsRes.data.tax_rule || '');
        setDefaultStatus(credsRes.data.default_status || 'DRAFT');
      }
    } catch (error) {
      console.error('Failed to load client details:', error);
    }
  };

  const handleTestConnection = async () => {
    if (!selectedClientForEdit) {
      toast.error('Please select a client first');
      return;
    }

    setTestingConnection(true);
    setConnectionTestResult(null);

    try {
      const response = await axios.post(`/credentials/clients/${selectedClientForEdit}/test`);
      
      setConnectionTestResult({
        success: response.data.success || false,
        message: response.data.message || (response.data.success ? 'Connection successful' : 'Connection failed')
      });

      if (response.data.success) {
        toast.success('Connection test successful');
      } else {
        toast.error('Connection test failed');
      }
    } catch (error) {
      const errorMessage = error.response?.data?.error || error.message || 'Connection test failed';
      setConnectionTestResult({
        success: false,
        message: errorMessage
      });
      toast.error('Connection test failed');
    } finally {
      setTestingConnection(false);
    }
  };

  // Mapping template handlers
  const handleCreateMapping = () => {
    setEditingMapping(null);
    setMappingName('');
    setColumnMapping({});
    setIsDefault(false);
    setCsvColumns([]);
    setShowMappingDialog(true);
  };

  const handleEditMapping = (mapping) => {
    setEditingMapping(mapping);
    setMappingName(mapping.mapping_name);
    setColumnMapping(mapping.column_mapping || {});
    setIsDefault(mapping.is_default);
    setCsvColumns([]);
    setShowMappingDialog(true);
  };

  const handleSaveMapping = async () => {
    if (!mappingName.trim()) {
      toast.error('Mapping name is required');
      return;
    }

    if (!selectedClientForEdit) {
      toast.error('Please select a client');
      return;
    }

    try {
      const payload = {
        client_erp_credentials_id: selectedClientForEdit,
        mapping_name: mappingName,
        column_mapping: columnMapping,
        is_default: isDefault
      };

      if (editingMapping) {
        await axios.put(`/mappings/${editingMapping.id}`, payload);
        toast.success('Mapping updated');
      } else {
        await axios.post('/mappings', payload);
        toast.success('Mapping created');
      }

      setShowMappingDialog(false);
      loadClientDetails();
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to save mapping');
    }
  };

  const handleColumnMappingChange = (cin7Field, csvColumn) => {
    setColumnMapping(prev => ({
      ...prev,
      [cin7Field]: csvColumn || null
    }));
  };

  // Cin7 field options for mapping
  // Note: CustomerID, CustomerEmail, SaleOrderNumber, InvoiceNumber, Status, Location
  // are auto-generated or handled automatically via lookups, so they're not shown here
  const cin7Fields = [
    { value: 'CustomerName', label: 'Customer Name (Lookup)', category: 'Customer', required: true },
    { value: 'CustomerReference', label: 'Customer Reference (PO#)', category: 'Order', required: true },
    { value: 'SaleDate', label: 'Sale Date', category: 'Order', required: true },
    { value: 'Currency', label: 'Currency', category: 'Order', required: false },
    { value: 'TaxInclusive', label: 'Tax Inclusive', category: 'Order', required: false },
    { value: 'SKU', label: 'Product SKU (Item Code)', category: 'Line Item', required: true },
    { value: 'Quantity', label: 'Quantity', category: 'Line Item', required: false },
    { value: 'Price', label: 'Price', category: 'Line Item', required: true },
    { value: 'Discount', label: 'Discount', category: 'Line Item', required: false },
    { value: 'Tax', label: 'Tax', category: 'Line Item', required: false },
  ];

  const groupedFields = cin7Fields.reduce((acc, field) => {
    if (!acc[field.category]) {
      acc[field.category] = [];
    }
    acc[field.category].push(field);
    return acc;
  }, {});

  const handleCreateClient = async () => {
    if (!newClientName.trim()) {
      toast.error('Client name is required');
      return;
    }

    setLoading(true);
    try {
      await axios.post('/clients', { name: newClientName.trim(), active: true });
      toast.success('Client created successfully');
      setShowCreateClient(false);
      setNewClientName('');
      refreshClients();
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to create client');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteClient = async () => {
    if (!clientToDelete) return;

    try {
      await axios.delete(`/clients/${clientToDelete}`);
      toast.success('Client deleted successfully');
      refreshClients();
      if (selectedClientForEdit === clientToDelete) {
        setSelectedClientForEdit(null);
      }
      setDeleteDialogOpen(false);
      setClientToDelete(null);
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to delete client');
    }
  };

  const openDeleteDialog = (clientId) => {
    setClientToDelete(clientId);
    setDeleteDialogOpen(true);
  };

  const handleToggleClientActive = async (client) => {
    try {
      await axios.put(`/clients/${client.id}`, { ...client, active: !client.active });
      toast.success(`Client ${!client.active ? 'activated' : 'deactivated'}`);
      refreshClients();
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to update client');
    }
  };

  const handleSearchUsers = async (query) => {
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }

    setSearchingUsers(true);
    try {
      const response = await axios.get(`/admin/users/search?q=${encodeURIComponent(query)}`);
      setSearchResults(response.data || []);
    } catch (error) {
      console.error('Error searching users:', error);
      setSearchResults([]);
    } finally {
      setSearchingUsers(false);
    }
  };

  const handleAddUser = async (userId, clientId) => {
    if (!clientId) {
      toast.error('Please select a client');
      return;
    }

    try {
      await axios.post(`/admin/clients/${clientId}/users`, {
        user_id: userId
      });
      toast.success('User assigned to client successfully');
      loadAllUsers(); // Reload all users to refresh the table
    } catch (error) {
      const errorMessage = error.response?.data?.error || error.message || 'Failed to assign user to client';
      console.error('Error assigning user to client:', error);
      console.error('Error details:', error.response?.data);
      toast.error(errorMessage);
    }
  };

  const loadAllUsers = async () => {
    setLoadingUsers(true);
    try {
      const response = await axios.get('/admin/users');
      console.log('Users response:', response.data);
      setAllUsers(response.data || []);
      if (response.data && response.data.length === 0) {
        console.warn('No users returned from API');
      }
    } catch (error) {
      console.error('Error loading users:', error);
      console.error('Error response:', error.response?.data);
      console.error('Error status:', error.response?.status);
      // Show error message to user
      if (error.response?.status === 403) {
        toast.error('Access denied. Admin role required to view users.');
      } else if (error.response?.status === 401) {
        toast.error('Please log in to view users.');
      } else {
        toast.error(`Failed to load users: ${error.response?.data?.error || error.message}`);
      }
      setAllUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const parseEnvFile = () => {
    if (!envFileContent.trim()) {
      return {};
    }

    // Parse .env content
    const lines = envFileContent.split('\n');
    const envVars = {};
    
    for (const line of lines) {
      const trimmed = line.trim();
      // Skip empty lines and comments
      if (!trimmed || trimmed.startsWith('#')) continue;
      
      // Parse KEY=VALUE
      const equalIndex = trimmed.indexOf('=');
      if (equalIndex === -1) continue;
      
      const key = trimmed.substring(0, equalIndex).trim();
      let value = trimmed.substring(equalIndex + 1).trim();
      
      // Remove quotes if present
      if ((value.startsWith('"') && value.endsWith('"')) || 
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      
      if (key && value) {
        envVars[key] = value;
      }
    }
    
    return envVars;
  };

  const loadDeploymentConfig = async () => {
    setLoadingConfig(true);
    try {
      const response = await axios.get('/admin/deployment/config');
      const config = response.data;
      setServiceName(config.service_name || 'cin7-uploader');
      setRegion(config.region || 'us-central1');
      
      // Convert env vars object back to .env format
      if (config.environment_variables && Object.keys(config.environment_variables).length > 0) {
        const envContent = Object.entries(config.environment_variables)
          .map(([key, value]) => `${key}=${value}`)
          .join('\n');
        setEnvFileContent(envContent);
      } else {
        setEnvFileContent('');
      }
    } catch (error) {
      console.error('Error loading deployment config:', error);
      if (error.response?.status !== 404) {
        toast.error('Failed to load deployment configuration');
      }
    } finally {
      setLoadingConfig(false);
    }
  };

  const saveDeploymentConfig = async () => {
    const envVars = parseEnvFile();
    
    if (Object.keys(envVars).length === 0 && !envFileContent.trim()) {
      toast.error('Please paste your .env file content');
      return;
    }
    
    setSavingConfig(true);
    try {
      const response = await axios.post('/admin/deployment/config', {
        service_name: serviceName,
        region: region,
        environment_variables: envVars
      });
      
      toast.success('Deployment configuration saved successfully!');
    } catch (error) {
      console.error('Error saving deployment config:', error);
      const errorMessage = error.response?.data?.error || 'Failed to save deployment configuration';
      toast.error(errorMessage);
    } finally {
      setSavingConfig(false);
    }
  };


  const handleUpdateUserRole = async (userId, newRole) => {
    try {
      await axios.put(`/admin/users/${userId}/role`, {
        role: newRole
      });
      toast.success('User role updated');
      loadAllUsers(); // Reload all users
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to update role');
      loadAllUsers(); // Reload to revert UI
    }
  };

  const handleRemoveUserFromClient = async (userId, clientId) => {
    try {
      await axios.delete(`/admin/clients/${clientId}/users/${userId}`);
      toast.success('User removed from client');
      loadAllUsers(); // Reload all users to refresh the table
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to remove user from client');
    }
  };

  const loadWorkflow = async () => {
    setLoadingWorkflow(true);
    try {
      const response = await axios.get(`/admin/workflow`);
      setWorkflowData(response.data);
    } catch (error) {
      console.error('Failed to load workflow:', error);
      toast.error('Failed to load workflow data');
    } finally {
      setLoadingWorkflow(false);
    }
  };


  return (
    <div className="p-6 space-y-6 h-full flex flex-col overflow-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">Admin</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Manage clients, users, and settings
          </p>
        </div>
      </div>

      <Tabs 
        defaultValue="clients" 
        className="flex-1"
        onValueChange={(value) => {
          if (value === 'workflow') {
            loadWorkflow();
          } else if (value === 'deployment') {
            loadDeploymentConfig();
          }
        }}
      >
        <TabsList>
          <TabsTrigger value="clients">
            <Building2 className="w-4 h-4 mr-2" />
            Clients
          </TabsTrigger>
          <TabsTrigger value="users">
            <Users className="w-4 h-4 mr-2" />
            Users
          </TabsTrigger>
          <TabsTrigger value="workflow">
            <Workflow className="w-4 h-4 mr-2" />
            Workflow
          </TabsTrigger>
          <TabsTrigger value="deployment">
            <Cloud className="w-4 h-4 mr-2" />
            Deployment
          </TabsTrigger>
        </TabsList>
        <div className="mb-4"></div>

        <TabsContent value="clients" className="space-y-6 mt-4">
          <div className="grid grid-cols-[1fr_3fr] gap-4 items-start">
            {/* Left Column: Clients Table */}
            <div className="flex flex-col">
              <Card className="border-0 shadow-none flex-1 flex flex-col" style={{ borderBottom: 'none', boxShadow: 'none' }}>
                <CardHeader className="px-0 pb-2 pt-0 flex flex-col space-y-1.5">
                  <div>
                    <CardTitle className="text-sm">Clients</CardTitle>
                    <CardDescription className="text-xs">Manage client profiles</CardDescription>
                  </div>
                </CardHeader>
                <CardContent className="px-0 pb-0 pt-0 flex-1 overflow-auto" style={{ paddingBottom: 0 }}>
                  {/* Status Filter Tabs */}
                  <div className="mb-2">
                    <Tabs value={clientStatusFilter} onValueChange={setClientStatusFilter} className="w-fit">
                      <TabsList className="mb-0 !justify-start w-fit h-9 p-1">
                        <TabsTrigger value="active" className="text-xs py-1.5">
                          Active
                        </TabsTrigger>
                        <TabsTrigger value="inactive" className="text-xs py-1.5">
                          Inactive
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                  </div>
                  <div className="rounded-md border overflow-hidden" style={{ marginBottom: 0 }}>
                    <Table className="border-0">
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">Name</TableHead>
                          <TableHead className="text-right text-xs">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(() => {
                          const filteredClients = allClients.filter(client => {
                            if (clientStatusFilter === 'active') return client.active !== false;
                            if (clientStatusFilter === 'inactive') return client.active === false;
                            return true;
                          });
                          
                          return filteredClients.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={2} className="text-center text-muted-foreground py-8">
                                No {clientStatusFilter} clients found.
                              </TableCell>
                            </TableRow>
                          ) : (
                            filteredClients.map((client) => (
                              <TableRow
                                key={client.id}
                                className={selectedClientForEdit === client.id ? 'bg-muted/50' : 'cursor-pointer'}
                                onClick={() => setSelectedClientForEdit(client.id)}
                              >
                                <TableCell className="font-medium text-xs">{client.name}</TableCell>
                                <TableCell className="text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 text-xs"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleToggleClientActive(client);
                                    }}
                                  >
                                    {client.active ? 'Deactivate' : 'Activate'}
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 text-xs"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      openDeleteDialog(client.id);
                                    }}
                                  >
                                    <Trash2 className="w-3 h-3 mr-1 text-destructive" />
                                    Delete
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          ))
                        );
                        })()}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Right Column: Selected Client Tabs */}
            <div className="flex flex-col">
              {selectedClientForEdit ? (
                <div className="flex-1 flex flex-col min-h-0">
            <Tabs 
              defaultValue="credentials" 
              className="w-full flex-1 flex flex-col"
            >
              {/* Spacer to align with left column CardHeader - exact match */}
              <div className="px-0 pb-2 pt-0 flex flex-col space-y-1.5">
                <div>
                  <h3 className="text-sm font-semibold leading-none tracking-tight opacity-0 pointer-events-none select-none">Clients</h3>
                  <p className="text-xs text-muted-foreground opacity-0 pointer-events-none select-none">Manage client profiles</p>
                </div>
              </div>
              <div className="mb-2">
                <TabsList className="mb-0 !justify-start w-fit h-9 p-1">
                  <TabsTrigger value="credentials" className="text-xs py-1.5">
                    <Key className="w-3 h-3 mr-1.5" />
                    Credentials
                  </TabsTrigger>
                  <TabsTrigger value="settings" className="text-xs py-1.5">
                    <SettingsIcon className="w-3 h-3 mr-1.5" />
                    Cin7 Defaults
                  </TabsTrigger>
                  <TabsTrigger value="mappings" className="text-xs py-1.5">
                    <FileText className="w-3 h-3 mr-1.5" />
                    CSV Mappings
                  </TabsTrigger>
                </TabsList>
              </div>

              <TabsContent value="credentials" className="space-y-3 mt-0 flex-1 overflow-auto">
                <Card className="shadow-none">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm">Cin7 Credentials</CardTitle>
                    <CardDescription className="text-xs">
                      Configure API credentials for{' '}
                      {allClients.find((c) => c.id === selectedClientForEdit)?.name}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {credentials ? (
                      <div className="space-y-3">
                        <div>
                          <Label className="text-xs">Account ID</Label>
                          <Input value={credentials.account_id} disabled className="h-8 text-xs" />
                        </div>
                        <div>
                          <Label className="text-xs">Application Key</Label>
                          <Input
                            type="password"
                            value={credentials.application_key}
                            disabled
                            className="h-8 text-xs"
                          />
                        </div>
                        <div className="flex gap-2 pt-1">
                          <Button
                            onClick={handleTestConnection}
                            disabled={testingConnection}
                            variant="outline"
                            size="sm"
                            className="h-8 text-xs"
                          >
                            {testingConnection ? 'Testing...' : 'Test Connection'}
                          </Button>
                          <Button size="sm" className="h-8 text-xs">Edit Credentials</Button>
                        </div>
                        {connectionTestResult && (
                          <div className={`p-2 rounded-md text-xs ${
                            connectionTestResult.success 
                              ? 'bg-green-50 text-green-800 border border-green-200' 
                              : 'bg-red-50 text-red-800 border border-red-200'
                          }`}>
                            <div className="font-medium text-xs">
                              {connectionTestResult.success ? '✓ Connection Successful' : '✗ Connection Failed'}
                            </div>
                            <div className="text-xs mt-1">
                              {connectionTestResult.message}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-6 text-muted-foreground text-xs">
                        No credentials configured. Click "Configure" to add Cin7 API credentials.
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="settings" className="space-y-3 mt-0 flex-1 overflow-auto">
              <Card className="shadow-none">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">Order Defaults</CardTitle>
                  <CardDescription className="text-xs">
                    Default values for sales orders from{' '}
                    {allClients.find((c) => c.id === selectedClientForEdit)?.name}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-3">
                    <div>
                      <Label htmlFor="default-status" className="text-xs">Default Status *</Label>
                      <Select value={defaultStatus} onValueChange={setDefaultStatus}>
                        <SelectTrigger id="default-status" className="h-8 text-xs">
                          <SelectValue placeholder="Select default status" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="DRAFT">DRAFT</SelectItem>
                          <SelectItem value="ORDERING">ORDERING</SelectItem>
                          <SelectItem value="ORDERED">ORDERED</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Status to use for all sales orders created from CSV
                      </p>
                    </div>
                    
                    <div>
                      <Label htmlFor="sale-type" className="text-xs">Sale Type</Label>
                      <Select value={saleType} onValueChange={setSaleType}>
                        <SelectTrigger id="sale-type" className="h-8 text-xs">
                          <SelectValue placeholder="Select sale type" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Advanced">Advanced</SelectItem>
                          <SelectItem value="Simple">Simple</SelectItem>
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Sale type to use for all sales orders (optional)
                      </p>
                    </div>
                    
                    <div>
                      <Label htmlFor="tax-rule" className="text-xs">Tax Rule</Label>
                      <Input
                        id="tax-rule"
                        value={taxRule}
                        onChange={(e) => setTaxRule(e.target.value)}
                        placeholder="e.g., TaxExclusive, TaxInclusive, etc."
                        className="h-8 text-xs"
                      />
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Tax rule to use for all sales orders (optional)
                      </p>
                    </div>
                    
                    <Button
                      size="sm"
                      className="h-8 text-xs mt-2"
                      onClick={async () => {
                        try {
                          await axios.put(`/credentials/clients/${selectedClientForEdit}/settings`, {
                            default_status: defaultStatus,
                            sale_type: saleType,
                            tax_rule: taxRule
                          });
                          toast.success('Settings saved');
                          loadClientDetails();
                        } catch (error) {
                          toast.error(error.response?.data?.error || 'Failed to save settings');
                        }
                      }}
                    >
                      Save Settings
                    </Button>
                  </div>
                </CardContent>
              </Card>
              </TabsContent>

              <TabsContent value="mappings" className="space-y-3 mt-0 flex-1 overflow-auto">
                <Card className="shadow-none">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="text-sm">CSV Mapping Templates</CardTitle>
                        <CardDescription className="text-xs">
                          Configure how CSV columns map to Cin7 fields
                        </CardDescription>
                      </div>
                      <Button size="sm" onClick={() => {
                        setEditingMapping(null);
                        setShowMappingDialog(true);
                      }}>
                        <Plus className="h-3 w-3 mr-1.5" />
                        New Template
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {loadingMappings ? (
                      <div className="text-center py-8 text-muted-foreground">Loading mappings...</div>
                    ) : mappingTemplates.length === 0 ? (
                      <div className="text-center py-8 text-muted-foreground">
                        No mapping templates configured. Create one to get started.
                      </div>
                    ) : (
                      <div className="rounded-md border overflow-hidden">
                        <Table className="border-0">
                          <TableHeader>
                            <TableRow>
                              <TableHead>Name</TableHead>
                              <TableHead>Default</TableHead>
                              <TableHead>Fields Mapped</TableHead>
                              <TableHead>Updated</TableHead>
                              <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                          {mappingTemplates.map((mapping) => (
                            <TableRow key={mapping.id}>
                              <TableCell className="font-medium">{mapping.mapping_name}</TableCell>
                              <TableCell>
                                {mapping.is_default ? (
                                  <Badge variant="default">Default</Badge>
                                ) : (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={async () => {
                                      try {
                                        await axios.put(`/mappings/${mapping.id}`, {
                                          ...mapping,
                                          is_default: true
                                        });
                                        toast.success('Default mapping updated');
                                        loadClientDetails();
                                      } catch (error) {
                                        toast.error('Failed to set default mapping');
                                      }
                                    }}
                                    className="h-6"
                                  >
                                    Set Default
                                  </Button>
                                )}
                              </TableCell>
                              <TableCell>
                                {Object.keys(mapping.column_mapping || {}).length} fields
                              </TableCell>
                              <TableCell className="text-sm text-muted-foreground">
                                {mapping.updated_at
                                  ? new Date(mapping.updated_at).toLocaleDateString()
                                  : '-'}
                              </TableCell>
                              <TableCell className="text-right">
                                <div className="flex justify-end gap-2">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleEditMapping(mapping)}
                                  >
                                    <Edit className="h-4 w-4" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={async () => {
                                      if (!window.confirm('Are you sure you want to delete this mapping?')) return;
                                      try {
                                        await axios.delete(`/mappings/${mapping.id}`);
                                        toast.success('Mapping deleted');
                                        loadClientDetails();
                                      } catch (error) {
                                        toast.error('Failed to delete mapping');
                                      }
                                    }}
                                  >
                                    <Trash2 className="h-4 w-4 text-destructive" />
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

            </Tabs>
                </div>
              ) : (
                <Card className="border-0 shadow-none flex-1 flex items-center justify-center">
                  <CardContent className="text-center text-muted-foreground py-8">
                    <Building2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-xs">Select a client from the table to view details</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="workflow" className="space-y-6 mt-4">
          <Card className="shadow-none border-0">
            <CardHeader className="px-0 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">API Workflow</CardTitle>
                  <CardDescription className="text-xs">
                    Overview of API calls made to Cin7 and their structure
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-0">
              {loadingWorkflow ? (
                <div className="text-center py-8 text-muted-foreground">Loading workflow...</div>
              ) : !workflowData ? (
                <div className="text-center py-8 text-muted-foreground">
                  Click refresh to load workflow data
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Workflow Steps */}
                  {workflowData.flow && workflowData.flow.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold mb-4">Workflow Steps</h3>
                      <div className="font-mono text-sm bg-slate-50 rounded-lg p-4 border border-slate-200">
                        {workflowData.flow.map((step, idx) => (
                          <div key={step.step} className="relative pl-6 py-1">
                            {/* Connecting lines - code style tree */}
                            {idx > 0 && (
                              <>
                                {/* Vertical line from previous step */}
                                <div className="absolute left-0 top-0 w-px h-3 bg-slate-400" />
                                {/* Horizontal line to current step */}
                                <div className="absolute left-0 top-3 w-4 h-px bg-slate-400" />
                              </>
                            )}
                            {/* Vertical line continuing down (for all items except last) */}
                            {idx < workflowData.flow.length - 1 && (
                              <div className="absolute left-0 top-3 w-px bottom-0 bg-slate-400" />
                            )}
                            
                            <div className="relative z-10">
                              <div className="font-semibold text-slate-900">
                                {step.step}. {step.name}
                              </div>
                              {step.description && (
                                <div className="text-xs text-slate-600 mt-0.5 ml-4">
                                  {step.description}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* API Calls */}
                  {workflowData.api_calls && workflowData.api_calls.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold mb-3">API Calls</h3>
                      <div className="space-y-4">
                        {workflowData.api_calls.map((apiCall, idx) => (
                          <Card key={idx} className="border shadow-none">
                            <CardHeader className="pb-3">
                              <div className="flex items-center gap-2">
                                <Badge variant="outline" className="font-mono text-xs">
                                  {apiCall.method}
                                </Badge>
                                <code className="text-sm font-mono">{apiCall.endpoint}</code>
                              </div>
                              <CardDescription className="text-xs mt-2">
                                {apiCall.description}
                              </CardDescription>
                              <div className="text-xs text-muted-foreground mt-1">
                                Base URL: <code className="text-xs">{apiCall.base_url}</code>
                              </div>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              {/* Required Fields */}
                              {apiCall.required_fields && apiCall.required_fields.length > 0 && (
                                <div>
                                  <div className="text-xs font-semibold mb-2 text-destructive">
                                    Required Fields
                                  </div>
                                  <div className="flex flex-wrap gap-2">
                                    {apiCall.required_fields.map((field) => (
                                      <Badge key={field} variant="destructive" className="text-xs">
                                        {field}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Optional Fields */}
                              {apiCall.optional_fields && apiCall.optional_fields.length > 0 && (
                                <div>
                                  <div className="text-xs font-semibold mb-2 text-muted-foreground">
                                    Optional Fields
                                  </div>
                                  <div className="flex flex-wrap gap-2">
                                    {apiCall.optional_fields.map((field) => (
                                      <Badge key={field} variant="secondary" className="text-xs">
                                        {field}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Line Item Fields (for Sale Order) */}
                              {apiCall.line_item_fields && (
                                <div>
                                  <div className="text-xs font-semibold mb-2">Line Item Fields</div>
                                  {apiCall.line_item_fields.required && apiCall.line_item_fields.required.length > 0 && (
                                    <div className="mb-2">
                                      <div className="text-xs text-destructive mb-1">Required:</div>
                                      <div className="flex flex-wrap gap-2">
                                        {apiCall.line_item_fields.required.map((field) => (
                                          <Badge key={field} variant="destructive" className="text-xs">
                                            {field}
                                          </Badge>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  {apiCall.line_item_fields.optional && apiCall.line_item_fields.optional.length > 0 && (
                                    <div>
                                      <div className="text-xs text-muted-foreground mb-1">Optional:</div>
                                      <div className="flex flex-wrap gap-2">
                                        {apiCall.line_item_fields.optional.map((field) => (
                                          <Badge key={field} variant="secondary" className="text-xs">
                                            {field}
                                          </Badge>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Notes */}
                              {apiCall.notes && apiCall.notes.length > 0 && (
                                <div>
                                  <div className="text-xs font-semibold mb-2">Notes</div>
                                  <ul className="space-y-1 text-xs text-muted-foreground">
                                    {apiCall.notes.map((note, noteIdx) => (
                                      <li key={noteIdx} className="flex gap-2">
                                        <span>•</span>
                                        <span>{note}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Example Payload */}
                              {apiCall.example_payload && (
                                <div>
                                  <div className="text-xs font-semibold mb-2">Example Payload</div>
                                  <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-96">
                                    {JSON.stringify(apiCall.example_payload, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="users" className="space-y-6 mt-4">
          <Card className="border-0 shadow-none">
            <CardHeader className="px-0 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Users</CardTitle>
                  <CardDescription className="text-xs">Manage users and their client assignments</CardDescription>
                </div>
                <Button onClick={() => setShowAddUserDialog(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Add User
                </Button>
              </div>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <div className="rounded-md border overflow-hidden">
                <Table className="border-0">
                  <TableHeader>
                  <TableRow className="h-6">
                    <TableHead className="text-xs py-1 px-2 h-6">Email</TableHead>
                    <TableHead className="text-xs py-1 px-2 h-6">Name</TableHead>
                    <TableHead className="text-xs py-1 px-2 h-6">Role</TableHead>
                    <TableHead className="text-xs py-1 px-2 h-6">Clients</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allUsers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                        No users found. Add a user to get started.
                      </TableCell>
                    </TableRow>
                  ) : (
                    allUsers.map((user) => {
                      // Get global role from user object
                      const userRole = user.role || 'user';
                      const roleDisplay = userRole === 'admin' ? 'Admin' : 'User';
                      
                      return (
                        <TableRow
                          key={user.id}
                          className="h-7"
                        >
                          <TableCell className="font-medium text-xs py-0.5 px-2 h-7">
                            <div className="flex items-center gap-1.5">
                              <span>{user.email}</span>
                              {user.email && !user.email.endsWith('@paleblue.nyc') && (
                                <Badge 
                                  className="text-xs bg-purple-100 text-purple-700 border-purple-200 shadow-none hover:bg-purple-100 pointer-events-none py-0 px-1.5"
                                >
                                  External
                                </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-xs py-0.5 px-2 h-7">{user.name || '-'}</TableCell>
                          <TableCell className="py-0.5 px-2 h-7">
                            <Select
                              value={userRole}
                              onValueChange={(newRole) => handleUpdateUserRole(user.id, newRole)}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <SelectTrigger className="w-auto h-auto text-xs !border-0 shadow-none bg-transparent p-0 [&>svg]:hidden [&>span]:pr-2.5">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="user">User</SelectItem>
                                <SelectItem value="admin">Admin</SelectItem>
                              </SelectContent>
                            </Select>
                          </TableCell>
                          <TableCell 
                            className="cursor-pointer hover:bg-muted/50 min-w-[200px] relative py-0.5 px-2 h-7"
                            onClick={(e) => {
                              // Don't trigger if clicking on a badge remove button
                              if (e.target.closest('button') || e.target.closest('[role="option"]')) {
                                return;
                              }
                              e.stopPropagation();
                              // Find and click the select trigger
                              const selectTrigger = e.currentTarget.querySelector('[role="combobox"]');
                              if (selectTrigger) {
                                selectTrigger.click();
                              }
                            }}
                          >
                            <div className="flex flex-wrap gap-1 items-center relative z-10">
                              {user.clients && user.clients.length > 0 ? (
                                user.clients.map((assignment) => {
                                  const client = allClients.find(c => c.id === assignment.client_id);
                                  return (
                                    <Badge 
                                      key={assignment.client_id} 
                                      variant="secondary" 
                                      className="text-xs flex items-center gap-1 pr-1 z-20 relative"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <span>{client?.name || 'Unknown'}</span>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleRemoveUserFromClient(user.id, assignment.client_id);
                                        }}
                                        className="ml-1 hover:bg-destructive/20 rounded-full p-0.5 z-30 relative"
                                      >
                                        <X className="w-3 h-3" />
                                      </button>
                                    </Badge>
                                  );
                                })
                              ) : (
                                <span className="text-xs text-muted-foreground">Click to assign</span>
                              )}
                            </div>
                            <Select
                              value=""
                              onValueChange={(clientId) => {
                                if (clientId && clientId !== '') {
                                  handleAddUser(user.id, clientId);
                                }
                              }}
                            >
                              <SelectTrigger className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-0">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {allClients
                                  .filter(client => 
                                    // Show all clients/connections that aren't already assigned
                                    !user.clients?.some(uc => uc.client_id === client.id)
                                  )
                                  .map((client) => (
                                    <SelectItem key={client.id} value={client.id}>
                                      {client.name}
                                    </SelectItem>
                                  ))}
                                {allClients.filter(client => 
                                  !user.clients?.some(uc => uc.client_id === client.id)
                                ).length === 0 && (
                                  <SelectItem value="" disabled>No clients available</SelectItem>
                                )}
                              </SelectContent>
                            </Select>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
              </div>
            </CardContent>
          </Card>

        </TabsContent>

        <TabsContent value="deployment" className="space-y-6 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cloud className="w-5 h-5" />
                Cloud Run Environment Variables
              </CardTitle>
              <CardDescription>
                Store your environment variables in the database for easy management
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Service Configuration */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="service-name">Service Name</Label>
                  <Input
                    id="service-name"
                    value={serviceName}
                    onChange={(e) => setServiceName(e.target.value)}
                    placeholder="cin7-uploader"
                  />
                </div>
                <div>
                  <Label htmlFor="region">Region</Label>
                  <Input
                    id="region"
                    value={region}
                    onChange={(e) => setRegion(e.target.value)}
                    placeholder="us-central1"
                  />
                </div>
              </div>

              {/* Paste .env File */}
              <div>
                <Label htmlFor="env-content">Paste .env File Content</Label>
                <textarea
                  id="env-content"
                  value={envFileContent}
                  onChange={(e) => setEnvFileContent(e.target.value)}
                  placeholder={`DATABASE_URL=postgresql://...
SECRET_KEY=...
JWT_SECRET_KEY=...
CORS_ORIGINS=https://yourdomain.com`}
                  className="w-full min-h-[300px] p-3 border rounded-md font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  Paste your entire .env file content here
                </p>
              </div>

              {/* Save Button */}
              <div className="flex justify-end">
                <Button
                  onClick={saveDeploymentConfig}
                  disabled={savingConfig || loadingConfig || !envFileContent.trim()}
                >
                  {savingConfig ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-2" />
                      Save Configuration
                    </>
                  )}
                </Button>
              </div>

              {loadingConfig && (
                <div className="text-sm text-muted-foreground flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading saved configuration...
                </div>
              )}

              {/* Info */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-blue-800 dark:text-blue-200">
                      Configuration Saved
                    </p>
                    <p className="text-xs text-blue-700 dark:text-blue-300">
                      Your environment variables are stored in the database. 
                      You can retrieve them later or use the upload script to apply them to Cloud Run.
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Create Client Dialog */}
      <Dialog open={showCreateClient} onOpenChange={setShowCreateClient}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Client</DialogTitle>
            <DialogDescription>
              Create a new client profile for managing sales orders
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Client Name</Label>
              <Input
                value={newClientName}
                onChange={(e) => setNewClientName(e.target.value)}
                placeholder="Enter client name"
                autoFocus
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateClient(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateClient} disabled={loading}>
              {loading ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will delete the client from the system.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteClient} className="bg-destructive text-destructive-foreground">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Add User Dialog */}
      <Dialog open={showAddUserDialog} onOpenChange={setShowAddUserDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add User</DialogTitle>
            <DialogDescription>
              Search for a user by email to add them to the system
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="user-search">Search by Email</Label>
              <div className="relative flex-1">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  id="user-search"
                  type="text"
                  value={userSearchQuery}
                  onChange={(e) => {
                    const query = e.target.value;
                    setUserSearchQuery(query);
                    handleSearchUsers(query);
                  }}
                  placeholder="Enter email to search..."
                  className="pl-8"
                />
              </div>
            </div>

            {searchingUsers && (
              <div className="text-sm text-muted-foreground">Searching...</div>
            )}

            {searchResults.length > 0 && (
              <div className="space-y-2">
                <Label>Select User</Label>
                <div className="border rounded-md max-h-48 overflow-y-auto">
                  {searchResults.map((user) => (
                    <div
                      key={user.id}
                      className="flex items-center justify-between p-2 hover:bg-muted cursor-pointer border-b last:border-b-0"
                      onClick={() => {
                        setUserSearchQuery(user.email);
                        setSearchResults([user]);
                      }}
                    >
                      <div>
                        <div className="font-medium text-sm">{user.email}</div>
                        {user.name && (
                          <div className="text-xs text-muted-foreground">{user.name}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {userSearchQuery && searchResults.length === 0 && !searchingUsers && userSearchQuery.length >= 2 && (
              <div className="text-sm text-muted-foreground">
                No users found matching "{userSearchQuery}"
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowAddUserDialog(false);
              setUserSearchQuery('');
              setSearchResults([]);
            }}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                const selectedUser = searchResults.find(u => 
                  u.email.toLowerCase() === userSearchQuery.toLowerCase()
                ) || searchResults[0];
                
                if (selectedUser) {
                  // User exists, just refresh the list
                  setShowAddUserDialog(false);
                  setUserSearchQuery('');
                  setSearchResults([]);
                  loadAllUsers();
                  toast.success('User found. You can now assign clients to them in the table.');
                } else {
                  toast.error('Please select a user from the search results');
                }
              }}
              disabled={searchResults.length === 0 || !userSearchQuery}
            >
              Add User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      {/* Mapping Template Dialog */}
      <Dialog open={showMappingDialog} onOpenChange={setShowMappingDialog}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingMapping ? 'Edit Mapping Template' : 'Create New Mapping Template'}
            </DialogTitle>
            <DialogDescription>
              Map CSV columns to Cin7 fields. You can enter CSV column names manually.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="mapping-name">Mapping Name</Label>
              <Input
                id="mapping-name"
                value={mappingName}
                onChange={(e) => setMappingName(e.target.value)}
                placeholder="e.g., Default, Wholesale, Retail"
              />
            </div>

            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="is-default"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="rounded"
              />
              <Label htmlFor="is-default">Set as default mapping</Label>
            </div>

            <div className="space-y-4">
              <Label>Column Mapping</Label>
              {Object.keys(groupedFields).map((category) => (
                <div key={category} className="space-y-2">
                  <h4 className="text-sm font-semibold text-muted-foreground">{category}</h4>
                  <div className="space-y-2 pl-4">
                    {groupedFields[category].map((field) => {
                      const isMapped = columnMapping[field.value] && columnMapping[field.value].trim() !== '';
                      const isRequired = field.required;
                      
                      return (
                        <div key={field.value} className="flex items-center gap-2">
                          <Label className={`w-56 text-sm ${isRequired && !isMapped ? 'text-destructive' : ''}`}>
                            {field.label}
                            {isRequired && <span className="text-destructive ml-1">*</span>}
                          </Label>
                          <Input
                            className={`flex-1 ${isRequired && !isMapped ? 'border-destructive' : ''}`}
                            placeholder="Enter CSV column name"
                            value={columnMapping[field.value] || ''}
                            onChange={(e) => handleColumnMappingChange(field.value, e.target.value)}
                          />
                          {isMapped && (
                            <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                              Mapped
                            </Badge>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
              
              {/* Missing Required Fields Warning */}
              {(() => {
                const missingRequired = cin7Fields.filter(f => 
                  f.required && 
                  (!columnMapping[f.value] || !columnMapping[f.value].trim())
                );
                
                if (missingRequired.length > 0) {
                  return (
                    <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5" />
                        <div className="flex-1">
                          <div className="font-semibold text-yellow-800 mb-1">Missing Required Fields</div>
                          <div className="text-sm text-yellow-700">
                            The following required fields are not mapped:
                            <ul className="list-disc list-inside mt-1 space-y-1">
                              {missingRequired.map(f => (
                                <li key={f.value}>{f.label}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                }
                return null;
              })()}
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setShowMappingDialog(false)}>
                <X className="h-4 w-4 mr-2" />
                Cancel
              </Button>
              <Button onClick={handleSaveMapping}>
                <Save className="h-4 w-4 mr-2" />
                Save Mapping
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

    </div>
  );
};

export default Admin;

