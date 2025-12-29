import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog';
import { Plus, Edit, Trash2, Save, X, Star, StarOff, Loader2 } from 'lucide-react';
import { useClient } from '../contexts/ClientContext';

const CsvMappingConfig = () => {
  const { selectedClientId, selectedClient } = useClient();
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingMapping, setEditingMapping] = useState(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [mappingName, setMappingName] = useState('');
  const [columnMapping, setColumnMapping] = useState({});
  const [customerCodeField, setCustomerCodeField] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  // Cin7 field options
  // Note: CustomerID, CustomerCode, CustomerEmail, SaleOrderNumber, InvoiceNumber, Status, Location
  // are auto-generated or handled automatically via lookups, so they're not shown here
  // Note: Tags and AdditionalAttribute1-10 are handled separately via customer code field selector
  const cin7Fields = [
    { value: 'CustomerName', label: 'Customer Name (Lookup)', category: 'Customer' },
    { value: 'CustomerReference', label: 'Customer Reference (PO)', category: 'Order' },
    { value: 'SaleDate', label: 'Sale Date', category: 'Order' },
    { value: 'ShipBy', label: 'Required By / Due Date', category: 'Order' },
    { value: 'ShippingAddress', label: 'Ship To Address', category: 'Order' },
    { value: 'Currency', label: 'Currency', category: 'Order' },
    { value: 'TaxInclusive', label: 'Tax Inclusive', category: 'Order' },
    { value: 'SKU', label: 'Product SKU (Item Code)', category: 'Line Item' },
    { value: 'Quantity', label: 'Quantity (Cases)', category: 'Line Item' },
    { value: 'Total', label: 'Total', category: 'Line Item', isCalculationField: true },
    { value: 'Price', label: 'Price', category: 'Line Item', isCalculationField: true },
    { value: 'Discount', label: 'Discount', category: 'Line Item' },
    { value: 'Tax', label: 'Tax', category: 'Line Item' },
  ];

  // Customer code field options
  const customerCodeFieldOptions = [
    { value: 'Tags', label: 'Tags' },
    { value: 'AdditionalAttribute1', label: 'Additional Attribute 1' },
    { value: 'AdditionalAttribute2', label: 'Additional Attribute 2' },
    { value: 'AdditionalAttribute3', label: 'Additional Attribute 3' },
    { value: 'AdditionalAttribute4', label: 'Additional Attribute 4' },
    { value: 'AdditionalAttribute5', label: 'Additional Attribute 5' },
    { value: 'AdditionalAttribute6', label: 'Additional Attribute 6' },
    { value: 'AdditionalAttribute7', label: 'Additional Attribute 7' },
    { value: 'AdditionalAttribute8', label: 'Additional Attribute 8' },
    { value: 'AdditionalAttribute9', label: 'Additional Attribute 9' },
    { value: 'AdditionalAttribute10', label: 'Additional Attribute 10' },
  ];

  useEffect(() => {
    if (selectedClientId) {
      loadMappings();
    } else {
      setMappings([]);
    }
  }, [selectedClientId]);

  const loadMappings = async () => {
    if (!selectedClientId) return;
    
    setLoading(true);
    try {
      const response = await axios.get(`/mappings/clients/${selectedClientId}`);
      setMappings(response.data);
    } catch (error) {
      console.error('Failed to load mappings:', error);
      toast.error('Failed to load mappings');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateNew = () => {
    setEditingMapping(null);
    setMappingName('');
    setColumnMapping({});
    setCustomerCodeField('');
    setIsDefault(false);
    setIsDialogOpen(true);
  };

  const handleEdit = (mapping) => {
    setEditingMapping(mapping);
    setMappingName(mapping.mapping_name);
    setColumnMapping(mapping.column_mapping || {});
    // Extract customer_code_field from column_mapping (stored as _customer_code_field)
    setCustomerCodeField(mapping.column_mapping?._customer_code_field || '');
    setIsDefault(mapping.is_default);
    setIsDialogOpen(true);
  };

  const handleDelete = async (mappingId) => {
    if (!window.confirm('Are you sure you want to delete this mapping?')) return;

    try {
      await axios.delete(`/mappings/${mappingId}`);
      toast.success('Mapping deleted');
      loadMappings();
    } catch (error) {
      toast.error('Failed to delete mapping');
    }
  };

  const handleSetDefault = async (mappingId) => {
    try {
      const mapping = mappings.find(m => m.id === mappingId);
      if (!mapping) return;

      await axios.put(`/mappings/${mappingId}`, {
        ...mapping,
        is_default: true
      });
      toast.success('Default mapping updated');
      loadMappings();
    } catch (error) {
      toast.error('Failed to set default mapping');
    }
  };

  const handleSave = async () => {
    if (!mappingName.trim()) {
      toast.error('Mapping name is required');
      return;
    }

    if (!selectedClientId) {
      toast.error('Please select a client');
      return;
    }

    try {
      // Store customer_code_field in column_mapping as a special key (only if set)
      const columnMappingWithCodeField = {
        ...columnMapping,
      };
      if (customerCodeField && customerCodeField.trim()) {
        columnMappingWithCodeField._customer_code_field = customerCodeField;
      }
      
      const payload = {
        client_erp_credentials_id: selectedClientId,
        mapping_name: mappingName,
        column_mapping: columnMappingWithCodeField,
        is_default: isDefault
      };

      if (editingMapping) {
        await axios.put(`/mappings/${editingMapping.id}`, payload);
        toast.success('Mapping updated');
      } else {
        await axios.post('/mappings', payload);
        toast.success('Mapping created');
      }

      setIsDialogOpen(false);
      loadMappings();
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to save mapping');
    }
  };

  const handleColumnMappingChange = (cin7Field, csvColumn) => {
    setColumnMapping(prev => ({
      ...prev,
      [cin7Field]: (csvColumn && csvColumn.trim() && csvColumn !== '__none__') ? csvColumn : null
    }));
  };

  // Build grouped fields, adding the selected customer code field to Customer section
  const groupedFields = useMemo(() => {
    const grouped = cin7Fields.reduce((acc, field) => {
      if (!acc[field.category]) {
        acc[field.category] = [];
      }
      acc[field.category].push(field);
      return acc;
    }, {});

    // Add the selected customer code field to the Customer section (only if one is selected)
    if (customerCodeField && customerCodeField.trim() && grouped['Customer']) {
      const codeFieldOption = customerCodeFieldOptions.find(opt => opt.value === customerCodeField);
      if (codeFieldOption) {
        // Remove any existing customer code fields first (in case user changed selection)
        grouped['Customer'] = grouped['Customer'].filter(f => 
          !customerCodeFieldOptions.some(opt => opt.value === f.value)
        );
        // Add the selected one
        grouped['Customer'].push({
          value: customerCodeField,
          label: `${codeFieldOption.label} (Customer Code)`,
          category: 'Customer'
        });
      }
    }

    return grouped;
  }, [customerCodeField]);

  // Add the selected customer code field to the Customer section
  if (customerCodeField && groupedFields['Customer']) {
    const codeFieldOption = customerCodeFieldOptions.find(opt => opt.value === customerCodeField);
    if (codeFieldOption) {
      // Check if it's already in the list (shouldn't be, but just in case)
      const exists = groupedFields['Customer'].some(f => f.value === customerCodeField);
      if (!exists) {
        groupedFields['Customer'].push({
          value: customerCodeField,
          label: `${codeFieldOption.label} (Customer Code)`,
          category: 'Customer'
        });
      }
    }
  }

  if (!selectedClientId) {
    return (
      <div className="p-6">
        <div className="py-12 text-center">
          <p className="text-muted-foreground">
            Please select a client from the sidebar to configure CSV mappings.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 h-full overflow-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">CSV Mappings</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Configure how CSV columns map to Cin7 fields for {selectedClient?.name}
          </p>
        </div>
        <Button onClick={handleCreateNew} className="h-8 text-xs">
          <Plus className="h-3 w-3 mr-2" />
          New Mapping
        </Button>
      </div>

      {loading ? (
        <div className="py-12 text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
          <p className="text-sm text-muted-foreground mt-2">Loading mappings...</p>
        </div>
      ) : mappings.length === 0 ? (
        <div className="py-12 text-center">
          <p className="text-muted-foreground">
            No mappings configured. Create one to get started.
          </p>
        </div>
      ) : (
        <div className="border-[1px] rounded-md overflow-hidden bg-white">
          <Table className="border-0">
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Name</TableHead>
                <TableHead className="text-xs">Default</TableHead>
                <TableHead className="text-xs">Fields Mapped</TableHead>
                <TableHead className="text-xs">Updated</TableHead>
                <TableHead className="text-right text-xs">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
            {mappings.map((mapping) => (
              <TableRow key={mapping.id}>
                <TableCell className="font-medium text-xs">{mapping.mapping_name}</TableCell>
                    <TableCell>
                      {mapping.is_default ? (
                        <Badge variant="default" className="text-[10px] px-1.5 py-0 h-4 shadow-none">Default</Badge>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleSetDefault(mapping.id)}
                          className="h-6 text-xs"
                        >
                          <StarOff className="h-3 w-3" />
                        </Button>
                      )}
                    </TableCell>
                <TableCell className="text-xs">
                  {Object.keys(mapping.column_mapping || {}).length} fields
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {mapping.updated_at
                    ? new Date(mapping.updated_at).toLocaleDateString()
                    : '-'}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleEdit(mapping)}
                      className="h-6 text-xs"
                    >
                      <Edit className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(mapping.id)}
                      className="h-6 text-xs"
                    >
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        </div>
      )}

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-sm">
              {editingMapping ? 'Edit Mapping' : 'Create New Mapping'}
            </DialogTitle>
            <DialogDescription className="text-xs">
              Map CSV columns to Cin7 fields.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2 max-w-xs">
              <Label htmlFor="mapping-name" className="text-xs">Mapping Name</Label>
              <Input
                id="mapping-name"
                className="h-8 text-xs"
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
              <Label htmlFor="is-default" className="text-xs">Set as default mapping</Label>
            </div>

            <div className="space-y-4">
              <Label className="text-xs">Column Mapping</Label>
              {Object.keys(groupedFields).map((category) => (
                <div key={category} className="space-y-2">
                  <h4 className="text-xs font-semibold text-muted-foreground">{category}</h4>
                  {category === 'Customer' && (
                    <div className="space-y-2 pl-4 mb-3">
                      <div className="space-y-1">
                        <Label htmlFor="customer-code-field-select" className="text-xs">Customer Code Field (Optional):</Label>
                        <Select value={customerCodeField || 'none'} onValueChange={(value) => setCustomerCodeField(value === 'none' ? '' : value)}>
                          <SelectTrigger id="customer-code-field-select" className="h-8 text-xs w-full max-w-xs">
                            <SelectValue placeholder="None (match by name only)" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">None (match by name only)</SelectItem>
                            {customerCodeFieldOptions.map(option => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                          Optional: Select which Cin7 field to use for customer code matching. If not set, customers will only be matched by name.
                        </p>
                      </div>
                    </div>
                  )}
                  <div className="space-y-2 pl-4">
                    {groupedFields[category].map((field) => {
                      const hasQuantity = columnMapping['Quantity'] && columnMapping['Quantity'].trim() !== '';
                      const hasTotal = columnMapping['Total'] && columnMapping['Total'].trim() !== '';
                      const hasPrice = columnMapping['Price'] && columnMapping['Price'].trim() !== '';
                      const showCalculationNote = field.value === 'Price' && hasQuantity && hasTotal && !hasPrice;
                      
                      return (
                        <div key={field.value} className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Label className="w-48 text-xs">{field.label}:</Label>
                            <Input
                              className="flex-1 h-8 text-xs"
                              placeholder="Enter CSV column name (leave empty to calculate)"
                              value={columnMapping[field.value] || ''}
                              onChange={(e) => handleColumnMappingChange(field.value, e.target.value)}
                            />
                          </div>
                          {showCalculationNote && (
                            <p className="text-xs text-muted-foreground pl-52 italic">
                              Price will be calculated from {columnMapping['Total']} ÷ {columnMapping['Quantity']} if Price is not mapped
                            </p>
                          )}
                          {field.value === 'Price' && !hasPrice && (
                            <p className="text-xs text-muted-foreground pl-52">
                              Optional: Map directly or leave empty to calculate from Total ÷ Quantity (Cases)
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <Button variant="outline" onClick={() => setIsDialogOpen(false)} className="h-8 text-xs">
                <X className="h-3 w-3 mr-2" />
                Cancel
              </Button>
              <Button onClick={handleSave} className="h-8 text-xs">
                <Save className="h-3 w-3 mr-2" />
                Save Mapping
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default CsvMappingConfig;



