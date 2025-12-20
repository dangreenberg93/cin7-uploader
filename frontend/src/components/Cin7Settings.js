import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useClient } from '../contexts/ClientContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Loader2 } from 'lucide-react';

const Cin7Settings = () => {
  const { selectedClientId, selectedClient } = useClient();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [defaultStatus, setDefaultStatus] = useState('DRAFT');
  const [saleType, setSaleType] = useState('');
  const [taxRule, setTaxRule] = useState('');
  // Track original values to detect changes
  const [originalValues, setOriginalValues] = useState({
    defaultStatus: 'DRAFT',
    saleType: '',
    taxRule: ''
  });

  useEffect(() => {
    if (selectedClientId) {
      loadSettings();
    } else {
      // Reset when no client selected
      setDefaultStatus('DRAFT');
      setSaleType('');
      setTaxRule('');
      setOriginalValues({
        defaultStatus: 'DRAFT',
        saleType: '',
        taxRule: ''
      });
    }
  }, [selectedClientId]);

  const loadSettings = async () => {
    if (!selectedClientId) return;

    setLoading(true);
    try {
      const response = await axios.get(`/credentials/clients/${selectedClientId}`);
      const credentials = response.data;
      
      const loadedDefaultStatus = credentials.default_status || 'DRAFT';
      const loadedSaleType = credentials.sale_type || '';
      const loadedTaxRule = credentials.tax_rule || '';
      
      setDefaultStatus(loadedDefaultStatus);
      setSaleType(loadedSaleType);
      setTaxRule(loadedTaxRule);
      
      // Store original values for change detection
      setOriginalValues({
        defaultStatus: loadedDefaultStatus,
        saleType: loadedSaleType,
        taxRule: loadedTaxRule
      });
    } catch (error) {
      console.error('Failed to load settings:', error);
      toast.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedClientId) {
      toast.error('Please select a client first');
      return;
    }

    setSaving(true);
    try {
      await axios.put(`/credentials/clients/${selectedClientId}/settings`, {
        default_status: defaultStatus,
        sale_type: saleType,
        tax_rule: taxRule
      });
      toast.success('Settings saved successfully');
      
      // Update original values after successful save
      setOriginalValues({
        defaultStatus,
        saleType,
        taxRule
      });
    } catch (error) {
      toast.error(error.response?.data?.error || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  // Check if there are any changes
  const hasChanges = 
    defaultStatus !== originalValues.defaultStatus ||
    saleType !== originalValues.saleType ||
    taxRule !== originalValues.taxRule;

  if (!selectedClientId) {
    return (
      <div className="p-6">
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              Please select a client from the sidebar to configure Cin7.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 h-full overflow-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">Cin7 Config</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Configure order defaults for {selectedClient?.name}
          </p>
        </div>
      </div>

      {loading ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
            <p className="text-sm text-muted-foreground mt-2">Loading settings...</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Order Defaults</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 max-w-xs">
              <div>
                <Label htmlFor="default-status" className="text-xs">Default Status *</Label>
                <Select value={defaultStatus} onValueChange={setDefaultStatus}>
                  <SelectTrigger id="default-status" className="h-8 text-xs w-full">
                    <SelectValue placeholder="Select default status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="DRAFT">DRAFT</SelectItem>
                    <SelectItem value="ORDERING">ORDERING</SelectItem>
                    <SelectItem value="ORDERED">ORDERED</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Status to use for all sales orders created from CSV
                </p>
              </div>
              
              <div>
                <Label htmlFor="sale-type" className="text-xs">Sale Type</Label>
                <Select value={saleType} onValueChange={setSaleType}>
                  <SelectTrigger id="sale-type" className="h-8 text-xs w-full">
                    <SelectValue placeholder="Select sale type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Advanced">Advanced</SelectItem>
                    <SelectItem value="Simple">Simple</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Sale type to use for all sales orders (optional)
                </p>
              </div>
              
              <div>
                <Label htmlFor="tax-rule" className="text-xs">Tax Rule</Label>
                <Input
                  id="tax-rule"
                  className="h-8 text-xs w-full"
                  value={taxRule}
                  onChange={(e) => setTaxRule(e.target.value)}
                  placeholder="e.g., TaxExclusive, TaxInclusive, etc."
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Tax rule to use for all sales orders (optional)
                </p>
              </div>
              
              <Button
                onClick={handleSave}
                disabled={saving || !hasChanges}
                className="h-8 text-xs"
              >
                {saving ? (
                  <>
                    <Loader2 className="w-3 h-3 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save Settings'
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Cin7Settings;



