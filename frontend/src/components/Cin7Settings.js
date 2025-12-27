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
  const [defaultLocation, setDefaultLocation] = useState(undefined);
  const [locations, setLocations] = useState([]);
  const [loadingLocations, setLoadingLocations] = useState(false);
  const [customerAccountReceivable, setCustomerAccountReceivable] = useState(undefined);
  const [customerRevenueAccount, setCustomerRevenueAccount] = useState(undefined);
  const [customerTaxRule, setCustomerTaxRule] = useState(undefined);
  const [customerAttributeSet, setCustomerAttributeSet] = useState(undefined);
  const [accounts, setAccounts] = useState([]);
  const [taxRules, setTaxRules] = useState([]);
  const [attributeSets, setAttributeSets] = useState([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [loadingTaxRules, setLoadingTaxRules] = useState(false);
  const [loadingAttributeSets, setLoadingAttributeSets] = useState(false);
  // Track original values to detect changes
  const [originalValues, setOriginalValues] = useState({
    defaultStatus: 'DRAFT',
    saleType: '',
    taxRule: '',
    defaultLocation: '',
    customerAccountReceivable: '',
    customerRevenueAccount: '',
    customerTaxRule: '',
    customerAttributeSet: ''
  });

  useEffect(() => {
    if (selectedClientId) {
      loadSettings();
    } else {
      // Reset when no client selected
      setDefaultStatus('DRAFT');
      setSaleType('');
      setTaxRule('');
      setDefaultLocation(undefined);
      setLocations([]);
      setCustomerAccountReceivable(undefined);
      setCustomerRevenueAccount(undefined);
      setCustomerTaxRule(undefined);
      setCustomerAttributeSet(undefined);
      setAccounts([]);
      setTaxRules([]);
      setAttributeSets([]);
      setOriginalValues({
        defaultStatus: 'DRAFT',
        saleType: '',
        taxRule: '',
        defaultLocation: '',
        customerAccountReceivable: '',
        customerRevenueAccount: '',
        customerTaxRule: '',
        customerAttributeSet: ''
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
      const loadedDefaultLocation = credentials.default_location || undefined;
      const loadedCustomerAccountReceivable = credentials.customer_account_receivable || undefined;
      const loadedCustomerRevenueAccount = credentials.customer_revenue_account || undefined;
      const loadedCustomerTaxRule = credentials.customer_tax_rule || undefined;
      const loadedCustomerAttributeSet = credentials.customer_attribute_set || undefined;
      
      setDefaultStatus(loadedDefaultStatus);
      setSaleType(loadedSaleType);
      setTaxRule(loadedTaxRule);
      setDefaultLocation(loadedDefaultLocation);
      setCustomerAccountReceivable(loadedCustomerAccountReceivable);
      setCustomerRevenueAccount(loadedCustomerRevenueAccount);
      setCustomerTaxRule(loadedCustomerTaxRule);
      setCustomerAttributeSet(loadedCustomerAttributeSet);
      
      // Load locations, accounts, and tax rules from Cin7 (don't fail if these error)
      try {
        await loadLocations();
      } catch (locationError) {
        console.error('Failed to load locations (non-fatal):', locationError);
      }
      
      try {
        await loadAccounts();
      } catch (accountError) {
        console.error('Failed to load accounts (non-fatal):', accountError);
      }
      
      try {
        await loadTaxRules();
      } catch (taxError) {
        console.error('Failed to load tax rules (non-fatal):', taxError);
      }
      
      try {
        await loadAttributeSets();
      } catch (attrError) {
        console.error('Failed to load attribute sets (non-fatal):', attrError);
      }
      
      // Store original values for change detection
      setOriginalValues({
        defaultStatus: loadedDefaultStatus,
        saleType: loadedSaleType,
        taxRule: loadedTaxRule,
        defaultLocation: loadedDefaultLocation,
        customerAccountReceivable: loadedCustomerAccountReceivable,
        customerRevenueAccount: loadedCustomerRevenueAccount,
        customerTaxRule: loadedCustomerTaxRule,
        customerAttributeSet: loadedCustomerAttributeSet
      });
    } catch (error) {
      console.error('Failed to load settings:', error);
      toast.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const loadLocations = async () => {
    if (!selectedClientId) return;

    setLoadingLocations(true);
    try {
      const response = await axios.get(`/credentials/clients/${selectedClientId}/locations`);
      console.log('Full response from locations endpoint:', response.data);
      const locations = response.data.locations || [];
      console.log('Loaded locations from Cin7:', locations);
      console.log('Number of locations:', locations.length);
      setLocations(locations);
    } catch (error) {
      console.error('Failed to load locations from Cin7:', error);
      console.error('Error details:', error.response?.data);
      // Don't show toast error - locations are optional
      setLocations([]);
    } finally {
      setLoadingLocations(false);
    }
  };

  const loadAccounts = async () => {
    if (!selectedClientId) return;

    setLoadingAccounts(true);
    try {
      const response = await axios.get(`/credentials/clients/${selectedClientId}/accounts`);
      console.log('Full response from accounts endpoint:', response.data);
      const accounts = response.data.accounts || [];
      console.log('Loaded accounts from Cin7:', accounts);
      console.log('Number of accounts:', accounts.length);
      setAccounts(accounts);
    } catch (error) {
      console.error('Failed to load accounts from Cin7:', error);
      console.error('Error details:', error.response?.data);
      setAccounts([]);
    } finally {
      setLoadingAccounts(false);
    }
  };

  const loadTaxRules = async () => {
    if (!selectedClientId) return;

    setLoadingTaxRules(true);
    try {
      const response = await axios.get(`/credentials/clients/${selectedClientId}/tax-rules`);
      console.log('Full response from tax-rules endpoint:', response.data);
      const taxRules = response.data.tax_rules || [];
      console.log('Loaded tax rules from Cin7:', taxRules);
      console.log('Number of tax rules:', taxRules.length);
      setTaxRules(taxRules);
    } catch (error) {
      console.error('Failed to load tax rules from Cin7:', error);
      console.error('Error details:', error.response?.data);
      setTaxRules([]);
    } finally {
      setLoadingTaxRules(false);
    }
  };

  const loadAttributeSets = async () => {
    if (!selectedClientId) return;

    setLoadingAttributeSets(true);
    try {
      const response = await axios.get(`/credentials/clients/${selectedClientId}/attribute-sets`);
      console.log('Full response from attribute-sets endpoint:', response.data);
      // Check both attribute_sets and attributeSets keys
      const attributeSets = response.data.attribute_sets || response.data.attributeSets || [];
      console.log('Loaded attribute sets from Cin7:', attributeSets);
      console.log('Number of attribute sets:', attributeSets.length);
      if (attributeSets.length > 0) {
        console.log('First attribute set:', attributeSets[0]);
        console.log('Attribute set keys:', Object.keys(attributeSets[0]));
      }
      setAttributeSets(attributeSets);
    } catch (error) {
      console.error('Failed to load attribute sets from Cin7:', error);
      console.error('Error details:', error.response?.data);
      setAttributeSets([]);
    } finally {
      setLoadingAttributeSets(false);
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
        tax_rule: taxRule,
        default_location: defaultLocation || null,
        customer_account_receivable: customerAccountReceivable || null,
        customer_revenue_account: customerRevenueAccount || null,
        customer_tax_rule: customerTaxRule || null,
        customer_attribute_set: customerAttributeSet || null
      });
      toast.success('Settings saved successfully');
      
      // Update original values after successful save (convert undefined to empty string for comparison)
      setOriginalValues({
        defaultStatus,
        saleType,
        taxRule,
        defaultLocation: defaultLocation || '',
        customerAccountReceivable: customerAccountReceivable || '',
        customerRevenueAccount: customerRevenueAccount || '',
        customerTaxRule: customerTaxRule || '',
        customerAttributeSet: customerAttributeSet || ''
      });
    } catch (error) {
      console.error('Error saving settings:', error);
      console.error('Error response:', error.response?.data);
      toast.error(error.response?.data?.error || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  // Check if there are any changes (convert undefined to empty string for comparison)
  const hasChanges = 
    defaultStatus !== originalValues.defaultStatus ||
    saleType !== originalValues.saleType ||
    taxRule !== originalValues.taxRule ||
    (defaultLocation || '') !== originalValues.defaultLocation ||
    (customerAccountReceivable || '') !== originalValues.customerAccountReceivable ||
    (customerRevenueAccount || '') !== originalValues.customerRevenueAccount ||
    (customerTaxRule || '') !== originalValues.customerTaxRule ||
    (customerAttributeSet || '') !== originalValues.customerAttributeSet;

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
          <>
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
                
                <div>
                  <Label htmlFor="default-location" className="text-xs">Default Location</Label>
                  {loadingLocations ? (
                    <div className="flex items-center gap-2 h-8">
                      <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">Loading locations...</span>
                    </div>
                  ) : (
                    <Select value={defaultLocation} onValueChange={(value) => setDefaultLocation(value)}>
                      <SelectTrigger id="default-location" className="h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0">
                        <SelectValue placeholder="Select an option" className="!bg-transparent !px-0 !py-0 !rounded-none !font-normal" />
                      </SelectTrigger>
                      <SelectContent>
                        {locations.map((loc) => (
                          <SelectItem key={loc.id} value={loc.id}>
                            {loc.name} {loc.code ? `(${loc.code})` : ''}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  <p className="text-xs text-muted-foreground mt-1">
                    Default location/warehouse to use for sales orders (optional)
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
          <CardHeader>
            <CardTitle className="text-sm">Customer Defaults</CardTitle>
            <CardDescription className="text-xs">
              Default values used when creating new customers
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 max-w-xs">
              <div>
                <Label htmlFor="customer-account-receivable" className="text-xs">Account Receivable</Label>
                {loadingAccounts ? (
                  <div className="flex items-center gap-2 h-8">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Loading accounts...</span>
                  </div>
                ) : (
                  <Select value={customerAccountReceivable} onValueChange={(value) => setCustomerAccountReceivable(value)}>
                    <SelectTrigger id="customer-account-receivable" className="h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0">
                      <SelectValue placeholder="Select an option" className="!bg-transparent !px-0 !py-0 !rounded-none !font-normal" />
                    </SelectTrigger>
                    <SelectContent>
                      {accounts.map((account) => (
                        <SelectItem key={account.Code || account.Name} value={account.Code || account.Name}>
                          {account.Name} {account.Code ? `(${account.Code})` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  Default Account Receivable for new customers (optional)
                </p>
              </div>

              <div>
                <Label htmlFor="customer-revenue-account" className="text-xs">Revenue Account</Label>
                {loadingAccounts ? (
                  <div className="flex items-center gap-2 h-8">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Loading accounts...</span>
                  </div>
                ) : (
                  <Select value={customerRevenueAccount} onValueChange={(value) => setCustomerRevenueAccount(value)}>
                    <SelectTrigger id="customer-revenue-account" className="h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0">
                      <SelectValue placeholder="Select an option" className="!bg-transparent !px-0 !py-0 !rounded-none !font-normal" />
                    </SelectTrigger>
                    <SelectContent>
                      {accounts.map((account) => (
                        <SelectItem key={account.Code || account.Name} value={account.Code || account.Name}>
                          {account.Name} {account.Code ? `(${account.Code})` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  Default Revenue Account for new customers (optional)
                </p>
              </div>

              <div>
                <Label htmlFor="customer-tax-rule" className="text-xs">Tax Rule</Label>
                {loadingTaxRules ? (
                  <div className="flex items-center gap-2 h-8">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Loading tax rules...</span>
                  </div>
                ) : (
                  <Select value={customerTaxRule} onValueChange={(value) => setCustomerTaxRule(value)}>
                    <SelectTrigger id="customer-tax-rule" className="h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0">
                      <SelectValue placeholder="Select an option" className="!bg-transparent !px-0 !py-0 !rounded-none !font-normal" />
                    </SelectTrigger>
                    <SelectContent>
                      {taxRules.map((tax) => (
                        <SelectItem key={tax.ID} value={tax.ID}>
                          {tax.Name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  Default Tax Rule for new customers (optional)
                </p>
              </div>

              <div>
                <Label htmlFor="customer-attribute-set" className="text-xs">Attribute Set</Label>
                {loadingAttributeSets ? (
                  <div className="flex items-center gap-2 h-8">
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">Loading attribute sets...</span>
                  </div>
                ) : (
                  <Select value={customerAttributeSet} onValueChange={(value) => setCustomerAttributeSet(value)}>
                    <SelectTrigger id="customer-attribute-set" className="h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0">
                      <SelectValue placeholder="Select an option" className="!bg-transparent !px-0 !py-0 !rounded-none !font-normal" />
                    </SelectTrigger>
                    <SelectContent>
                      {attributeSets.map((attrSet) => (
                        <SelectItem key={attrSet.ID || attrSet.Name} value={attrSet.Name || attrSet.ID}>
                          {attrSet.Name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  Default Attribute Set for new customers (optional)
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
        </>
      )}
    </div>
  );
};

export default Cin7Settings;



