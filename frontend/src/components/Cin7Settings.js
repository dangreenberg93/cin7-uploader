import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useClient } from '../contexts/ClientContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Switch } from './ui/switch';
import { Badge } from './ui/badge';
import { Loader2, CheckCircle2, XCircle, RotateCcw } from 'lucide-react';

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
  // Auto-create settings (single combined setting)
  const [autoCreateCustomersProducts, setAutoCreateCustomersProducts] = useState(false);
  // Product defaults
  const [productCostingMethod, setProductCostingMethod] = useState('FIFO');
  const [productDefaultPriceTier, setProductDefaultPriceTier] = useState('Tier 1');
  const [productDefaultPrice, setProductDefaultPrice] = useState(0.0);
  const [productCurrency, setProductCurrency] = useState('USD');
  // Track original values to detect changes
  const [originalValues, setOriginalValues] = useState({
    defaultStatus: 'DRAFT',
    saleType: '',
    taxRule: '',
    defaultLocation: '',
    customerAccountReceivable: '',
    customerRevenueAccount: '',
    customerTaxRule: '',
    customerAttributeSet: '',
    autoCreateCustomersProducts: false,
    productCostingMethod: 'FIFO',
    productDefaultPriceTier: 'Tier 1',
    productDefaultPrice: 0.0,
    productCurrency: 'USD'
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
      setAutoCreateCustomersProducts(false);
      setProductCostingMethod('FIFO');
      setProductDefaultPriceTier('Tier 1');
      setProductDefaultPrice(0.0);
      setProductCurrency('USD');
      setOriginalValues({
        defaultStatus: 'DRAFT',
        saleType: '',
        taxRule: '',
        defaultLocation: '',
        customerAccountReceivable: '',
        customerRevenueAccount: '',
        customerTaxRule: '',
        customerAttributeSet: '',
        autoCreateCustomersProducts: false,
        productCostingMethod: 'FIFO',
        productDefaultPriceTier: 'Tier 1',
        productDefaultPrice: 0.0,
        productCurrency: 'USD'
      });
    }
  }, [selectedClientId]);

  const loadSettings = async () => {
    if (!selectedClientId) return;

    setLoading(true);
    try {
      // Load credentials
      const credentialsResponse = await axios.get(`/credentials/clients/${selectedClientId}`);
      const credentials = credentialsResponse.data;
      
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
      
      // Load auto-create setting from credentials (handle null/undefined explicitly)
      // Explicitly check for true/false to handle boolean values correctly
      const loadedAutoCreateCustomersProducts = credentials.auto_create_customers_products === true || credentials.auto_create_customers_products === 'true' || credentials.auto_create_customers_products === 1;
      console.log('Loaded auto_create_customers_products from credentials:', credentials.auto_create_customers_products, 'type:', typeof credentials.auto_create_customers_products, '->', loadedAutoCreateCustomersProducts);
      setAutoCreateCustomersProducts(loadedAutoCreateCustomersProducts);
      
      // Load product defaults from credentials
      const loadedProductCostingMethod = credentials.product_costing_method || 'FIFO';
      const loadedProductDefaultPriceTier = credentials.product_default_price_tier || 'Tier 1';
      const loadedProductDefaultPrice = credentials.product_default_price !== undefined ? credentials.product_default_price : 0.0;
      const loadedProductCurrency = credentials.product_currency || 'USD';
      
      setProductCostingMethod(loadedProductCostingMethod);
      setProductDefaultPriceTier(loadedProductDefaultPriceTier);
      setProductDefaultPrice(loadedProductDefaultPrice);
      setProductCurrency(loadedProductCurrency);
      
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
      
      // Store original values for change detection (convert undefined/null to empty string for consistency)
      setOriginalValues({
        defaultStatus: loadedDefaultStatus,
        saleType: loadedSaleType || '',
        taxRule: loadedTaxRule || '',
        defaultLocation: (loadedDefaultLocation || ''),
        customerAccountReceivable: (loadedCustomerAccountReceivable || ''),
        customerRevenueAccount: (loadedCustomerRevenueAccount || ''),
        customerTaxRule: (loadedCustomerTaxRule || ''),
        customerAttributeSet: (loadedCustomerAttributeSet || ''),
        autoCreateCustomersProducts: loadedAutoCreateCustomersProducts,
        productCostingMethod: loadedProductCostingMethod,
        productDefaultPriceTier: loadedProductDefaultPriceTier,
        productDefaultPrice: loadedProductDefaultPrice,
        productCurrency: loadedProductCurrency
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
      // Save credentials settings
      const payload = {
        default_status: defaultStatus,
        sale_type: saleType,
        tax_rule: taxRule,
        default_location: defaultLocation || null,
        customer_account_receivable: customerAccountReceivable || null,
        customer_revenue_account: customerRevenueAccount || null,
        customer_tax_rule: customerTaxRule || null,
        customer_attribute_set: customerAttributeSet || null,
        product_costing_method: productCostingMethod || null,
        product_default_price_tier: productDefaultPriceTier || null,
        product_default_price: productDefaultPrice !== undefined ? productDefaultPrice : null,
        product_currency: productCurrency || null,
        auto_create_customers_products: autoCreateCustomersProducts
      };
      console.log('Saving settings with payload:', payload);
      const response = await axios.put(`/credentials/clients/${selectedClientId}/settings`, payload);
      console.log('Save response:', response.data);
      
      toast.success('Settings saved successfully');
      
      // Update state from response to ensure we have the exact saved values
      if (response.data.auto_create_customers_products !== undefined) {
        const savedAutoCreate = response.data.auto_create_customers_products === true || response.data.auto_create_customers_products === 'true' || response.data.auto_create_customers_products === 1;
        console.log('Updating auto_create_customers_products from response:', response.data.auto_create_customers_products, '->', savedAutoCreate);
        setAutoCreateCustomersProducts(savedAutoCreate);
      }
      
      // Update original values after successful save (convert undefined to empty string for comparison)
      setOriginalValues({
        defaultStatus: response.data.default_status || defaultStatus,
        saleType: response.data.sale_type || saleType,
        taxRule: response.data.tax_rule || taxRule,
        defaultLocation: (response.data.default_location || ''),
        customerAccountReceivable: (response.data.customer_account_receivable || ''),
        customerRevenueAccount: (response.data.customer_revenue_account || ''),
        customerTaxRule: (response.data.customer_tax_rule || ''),
        customerAttributeSet: (response.data.customer_attribute_set || ''),
        autoCreateCustomersProducts: response.data.auto_create_customers_products !== undefined 
          ? (response.data.auto_create_customers_products === true || response.data.auto_create_customers_products === 'true' || response.data.auto_create_customers_products === 1)
          : autoCreateCustomersProducts,
        productCostingMethod: response.data.product_costing_method || productCostingMethod,
        productDefaultPriceTier: response.data.product_default_price_tier || productDefaultPriceTier,
        productDefaultPrice: response.data.product_default_price !== undefined ? response.data.product_default_price : productDefaultPrice,
        productCurrency: response.data.product_currency || productCurrency
      });
    } catch (error) {
      console.error('Error saving settings:', error);
      console.error('Error response:', error.response?.data);
      toast.error(error.response?.data?.error || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    // Reset all fields to their original values
    setDefaultStatus(originalValues.defaultStatus);
    setSaleType(originalValues.saleType);
    setTaxRule(originalValues.taxRule);
    setDefaultLocation(originalValues.defaultLocation || undefined);
    setCustomerAccountReceivable(originalValues.customerAccountReceivable || undefined);
    setCustomerRevenueAccount(originalValues.customerRevenueAccount || undefined);
    setCustomerTaxRule(originalValues.customerTaxRule || undefined);
    setCustomerAttributeSet(originalValues.customerAttributeSet || undefined);
    setAutoCreateCustomersProducts(originalValues.autoCreateCustomersProducts);
    setProductCostingMethod(originalValues.productCostingMethod);
    setProductDefaultPriceTier(originalValues.productDefaultPriceTier);
    setProductDefaultPrice(originalValues.productDefaultPrice);
    setProductCurrency(originalValues.productCurrency);
    toast.success('Settings reset to original values');
  };

  // Check if customer defaults are set up (required for auto-create)
  const isCustomerDefaultsSetUp = useMemo(() => {
    return !!(
      customerAccountReceivable &&
      customerRevenueAccount &&
      customerTaxRule
    );
  }, [customerAccountReceivable, customerRevenueAccount, customerTaxRule]);

  // Check if auto-create is ready (toggle ON and both customer and product defaults configured)
  const isAutoCreateReady = useMemo(() => {
    return autoCreateCustomersProducts && isCustomerDefaultsSetUp && !!productCostingMethod;
  }, [autoCreateCustomersProducts, isCustomerDefaultsSetUp, productCostingMethod]);

  // Check if there are any changes (convert undefined to empty string for comparison)
  const hasChanges = 
    defaultStatus !== originalValues.defaultStatus ||
    saleType !== originalValues.saleType ||
    taxRule !== originalValues.taxRule ||
    (defaultLocation || '') !== originalValues.defaultLocation ||
    (customerAccountReceivable || '') !== originalValues.customerAccountReceivable ||
    (customerRevenueAccount || '') !== originalValues.customerRevenueAccount ||
    (customerTaxRule || '') !== originalValues.customerTaxRule ||
    (customerAttributeSet || '') !== originalValues.customerAttributeSet ||
    autoCreateCustomersProducts !== originalValues.autoCreateCustomersProducts ||
    productCostingMethod !== originalValues.productCostingMethod ||
    productDefaultPriceTier !== originalValues.productDefaultPriceTier ||
    productDefaultPrice !== originalValues.productDefaultPrice ||
    productCurrency !== originalValues.productCurrency;

  // Helper functions to check if individual fields have changed
  const isFieldChanged = (fieldName) => {
    switch (fieldName) {
      case 'defaultStatus':
        return defaultStatus !== originalValues.defaultStatus;
      case 'saleType':
        return saleType !== originalValues.saleType;
      case 'taxRule':
        return taxRule !== originalValues.taxRule;
      case 'defaultLocation':
        return (defaultLocation || '') !== originalValues.defaultLocation;
      case 'customerAccountReceivable':
        return (customerAccountReceivable || '') !== originalValues.customerAccountReceivable;
      case 'customerRevenueAccount':
        return (customerRevenueAccount || '') !== originalValues.customerRevenueAccount;
      case 'customerTaxRule':
        return (customerTaxRule || '') !== originalValues.customerTaxRule;
      case 'customerAttributeSet':
        return (customerAttributeSet || '') !== originalValues.customerAttributeSet;
      case 'autoCreateCustomersProducts':
        return autoCreateCustomersProducts !== originalValues.autoCreateCustomersProducts;
      case 'productCostingMethod':
        return productCostingMethod !== originalValues.productCostingMethod;
      case 'productDefaultPriceTier':
        return productDefaultPriceTier !== originalValues.productDefaultPriceTier;
      case 'productDefaultPrice':
        return productDefaultPrice !== originalValues.productDefaultPrice;
      case 'productCurrency':
        return productCurrency !== originalValues.productCurrency;
      default:
        return false;
    }
  };

  // Helper function to get className for changed fields (reusable style)
  const getChangedFieldClassName = (fieldName, baseClassName = '') => {
    const changedClass = isFieldChanged(fieldName) ? '!border-blue-500' : '';
    return `${baseClassName} ${changedClass}`.trim();
  };

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
          <div className="flex items-center gap-2">
            <Button
              onClick={handleReset}
              disabled={!hasChanges}
              variant="outline"
              className="h-8 text-xs"
            >
              <RotateCcw className="w-3 h-3 mr-2" />
              Reset
            </Button>
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
                'Save All Settings'
              )}
            </Button>
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
                    <SelectTrigger id="default-status" className={getChangedFieldClassName('defaultStatus', 'h-8 text-xs w-full')}>
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
                    <SelectTrigger id="sale-type" className={getChangedFieldClassName('saleType', 'h-8 text-xs w-full')}>
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
                    className={getChangedFieldClassName('taxRule', 'h-8 text-xs w-full')}
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
                      <SelectTrigger id="default-location" className={getChangedFieldClassName('defaultLocation', 'h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0')}>
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
            <div className="flex items-center gap-3">
              <CardTitle className="text-sm">Auto-create Data Settings</CardTitle>
              <div className="flex items-center gap-2">
                {!autoCreateCustomersProducts ? (
                  <Badge variant="outline" className="text-xs bg-gray-50 text-gray-600 border-gray-200">
                    Inactive
                  </Badge>
                ) : isAutoCreateReady ? (
                  <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    Active
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs bg-red-50 text-red-700 border-red-200">
                    <XCircle className="h-3 w-3 mr-1" />
                    Not ready
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="auto-create-customers-products" className="text-xs">Auto-create</Label>
                <div className={isFieldChanged('autoCreateCustomersProducts') ? 'p-1 rounded-full border border-blue-500' : ''}>
                  <Switch
                    id="auto-create-customers-products"
                    checked={autoCreateCustomersProducts}
                    onCheckedChange={setAutoCreateCustomersProducts}
                  />
                </div>
              </div>
            </div>
            <CardDescription className="text-xs mt-1">
              Default values used when auto-creating customers and products
            </CardDescription>
          </CardHeader>
          <CardContent>
            {autoCreateCustomersProducts ? (
              <div className="space-y-6 max-w-xs">
                {(!isCustomerDefaultsSetUp || !productCostingMethod) && (
                  <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                    <p className="text-xs text-yellow-800 font-medium mb-1">Setup Required</p>
                    <p className="text-xs text-yellow-700">
                      {!isCustomerDefaultsSetUp && 'Please configure Account Receivable, Revenue Account, and Tax Rule. '}
                      {!productCostingMethod && 'Please configure Product Costing Method. '}
                      All required defaults must be set to enable auto-create.
                    </p>
                  </div>
                )}
                
                {/* Customer Defaults Section */}
                <div className="space-y-4">
                  <h4 className="text-xs font-semibold text-gray-700">Customer Defaults</h4>
                  <div>
                    <Label htmlFor="customer-account-receivable" className="text-xs">Account Receivable</Label>
                    {loadingAccounts ? (
                      <div className="flex items-center gap-2 h-8">
                        <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">Loading accounts...</span>
                      </div>
                    ) : (
                      <Select value={customerAccountReceivable} onValueChange={(value) => setCustomerAccountReceivable(value)}>
                        <SelectTrigger id="customer-account-receivable" className={getChangedFieldClassName('customerAccountReceivable', 'h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0')}>
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
                      Default Account Receivable for new customers <span className="text-red-500">*</span>
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
                        <SelectTrigger id="customer-revenue-account" className={getChangedFieldClassName('customerRevenueAccount', 'h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0')}>
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
                      Default Revenue Account for new customers <span className="text-red-500">*</span>
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
                        <SelectTrigger id="customer-tax-rule" className={getChangedFieldClassName('customerTaxRule', 'h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0')}>
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
                      Default Tax Rule for new customers <span className="text-red-500">*</span>
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
                        <SelectTrigger id="customer-attribute-set" className={getChangedFieldClassName('customerAttributeSet', 'h-8 text-xs w-full [&:not([data-placeholder])>span]:!bg-transparent [&:not([data-placeholder])>span]:!px-0 [&:not([data-placeholder])>span]:!py-0 [&:not([data-placeholder])>span]:!rounded-none [&:not([data-placeholder])>span]:!font-normal [&:not([data-placeholder])>span]:!mr-0')}>
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
                </div>
                
                {/* Product Defaults Section */}
                <div className="space-y-4">
                  <h4 className="text-xs font-semibold text-gray-700">Product Defaults</h4>
                  <div>
                    <Label htmlFor="product-costing-method" className="text-xs">
                      Costing Method <span className="text-red-500">*</span>
                    </Label>
                    <Select value={productCostingMethod} onValueChange={setProductCostingMethod}>
                      <SelectTrigger id="product-costing-method" className={getChangedFieldClassName('productCostingMethod', 'h-8 text-xs w-full')}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="FIFO">FIFO</SelectItem>
                        <SelectItem value="LIFO">LIFO</SelectItem>
                        <SelectItem value="Average">Average</SelectItem>
                        <SelectItem value="Standard">Standard</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground mt-1">
                      Default costing method for new products
                    </p>
                  </div>
                  
                  <div>
                    <Label htmlFor="product-price-tier" className="text-xs">Default Price Tier</Label>
                    <Input
                      id="product-price-tier"
                      className={getChangedFieldClassName('productDefaultPriceTier', 'h-8 text-xs w-full')}
                      value={productDefaultPriceTier}
                      onChange={(e) => setProductDefaultPriceTier(e.target.value)}
                      placeholder="Tier 1"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Default price tier name (e.g., "Tier 1")
                    </p>
                  </div>
                  
                  <div>
                    <Label htmlFor="product-default-price" className="text-xs">Default Price</Label>
                    <Input
                      id="product-default-price"
                      type="number"
                      step="0.01"
                      className={getChangedFieldClassName('productDefaultPrice', 'h-8 text-xs w-full')}
                      value={productDefaultPrice}
                      onChange={(e) => setProductDefaultPrice(parseFloat(e.target.value) || 0.0)}
                      placeholder="0.00"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Default price for new products
                    </p>
                  </div>
                  
                  <div>
                    <Label htmlFor="product-currency" className="text-xs">Currency</Label>
                    <Input
                      id="product-currency"
                      className={getChangedFieldClassName('productCurrency', 'h-8 text-xs w-full')}
                      value={productCurrency}
                      onChange={(e) => setProductCurrency(e.target.value)}
                      placeholder="USD"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Currency for new products
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-sm text-muted-foreground">
                Enable auto-create to configure default settings
              </div>
            )}
          </CardContent>
        </Card>
        </>
      )}
    </div>
  );
};

export default Cin7Settings;



