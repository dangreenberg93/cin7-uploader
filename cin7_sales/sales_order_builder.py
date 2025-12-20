"""
Sales Order Builder - Transforms CSV data into Cin7 sales order format
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid


class SalesOrderBuilder:
    """Builds Cin7 sales order payloads from CSV data"""
    
    def __init__(self, settings: Dict[str, Any], api_client=None, 
                 preloaded_customers: Optional[Dict[str, Any]] = None,
                 preloaded_products: Optional[Dict[str, Any]] = None):
        """
        Initialize the builder.
        
        Args:
            settings: Client settings (defaults, etc.)
            api_client: Optional Cin7SalesAPI client for lookups
            preloaded_customers: Optional preloaded customer lookup dict (by name/ID)
            preloaded_products: Optional preloaded product lookup dict (by SKU)
        """
        self.settings = settings
        self.api_client = api_client
        self._customer_cache = {}  # Cache customer lookups by name
        self._product_cache = {}  # Cache product lookups by SKU
        self.preloaded_customers = preloaded_customers or {}  # Use preloaded data if available
        self.preloaded_products = preloaded_products or {}  # Use preloaded data if available
    
    def build_sale(self, row_data: Dict[str, Any], column_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Build a Cin7 Sale payload from CSV row data.
        Sale includes: Customer, CustomerID, BillingAddress, ShippingAddress, 
        ShipBy, CustomerReference, Status, Type
        
        Args:
            row_data: Raw CSV row data
            column_mapping: Mapping of Cin7 fields to CSV columns
        
        Returns:
            Cin7 Sale dictionary
        """
        # Extract mapped values
        mapped = {}
        for cin7_field, csv_column in column_mapping.items():
            if csv_column and csv_column in row_data:
                mapped[cin7_field] = row_data[csv_column]
        
        # Build Sale payload
        # Determine Type based on sale_type setting: "Advanced" -> "Advanced Sale", "Simple" -> "Simple Sale"
        sale_type_setting = self.settings.get('sale_type', '').strip()
        if sale_type_setting.lower() == 'advanced':
            sale_type_value = 'Advanced Sale'
        elif sale_type_setting.lower() == 'simple':
            sale_type_value = 'Simple Sale'
        else:
            # Default to "Simple Sale" if not set or invalid
            sale_type_value = 'Simple Sale'
        
        # Build Sale payload - CustomerID and Type are required
        sale = {
            'Type': sale_type_value  # Set Type based on client settings: "Advanced Sale" or "Simple Sale"
        }
        
        # Customer - prioritize lookup by name to get IDs
        customer_data = None
        if 'CustomerName' in mapped and mapped['CustomerName']:
            # Lookup customer by name to get CustomerID, ShippingAddressID, BillingAddressID
            customer_data = self._lookup_customer_by_name(mapped['CustomerName'])
            if customer_data:
                sale['CustomerID'] = customer_data.get('ID')
                # Get shipping and billing address IDs if available and valid
                shipping_address = customer_data.get('ShippingAddress')
                if shipping_address and isinstance(shipping_address, dict) and shipping_address.get('ID'):
                    sale['ShippingAddress'] = shipping_address.get('ID')
                billing_address = customer_data.get('BillingAddress')
                if billing_address and isinstance(billing_address, dict) and billing_address.get('ID'):
                    sale['BillingAddress'] = billing_address.get('ID')
                # Set Customer name from lookup
                sale['Customer'] = customer_data.get('Name') or mapped['CustomerName']
            else:
                # Fallback: use name directly
                sale['Customer'] = mapped['CustomerName']
        elif 'CustomerID' in mapped and mapped['CustomerID']:
            sale['CustomerID'] = mapped['CustomerID']
            # Try to get customer data for name and addresses
            customer_data = None
            
            # First check preloaded data (avoid API calls)
            if self.preloaded_customers:
                # Check if customer is in preloaded data by ID (stored directly by ID key)
                customer_data = self.preloaded_customers.get(mapped['CustomerID'])
            
            # Only fallback to API if not found in preloaded data AND preloaded data exists (avoid API calls)
            if not customer_data and self.api_client and not self.preloaded_customers:
                customer_data = self.api_client.get_customer(mapped['CustomerID'])
            
            if customer_data:
                sale['Customer'] = customer_data.get('Name')
                shipping_address = customer_data.get('ShippingAddress')
                if shipping_address and isinstance(shipping_address, dict) and shipping_address.get('ID'):
                    sale['ShippingAddress'] = shipping_address.get('ID')
                billing_address = customer_data.get('BillingAddress')
                if billing_address and isinstance(billing_address, dict) and billing_address.get('ID'):
                    sale['BillingAddress'] = billing_address.get('ID')
        
        # BillingAddress - override if explicitly provided
        if 'BillingAddress' in mapped and mapped['BillingAddress']:
            try:
                billing_addr_value = str(uuid.UUID(mapped['BillingAddress']))
                if billing_addr_value:  # Only set if not empty
                    sale['BillingAddress'] = billing_addr_value
            except ValueError:
                # If not a UUID, might be an address object - pass as-is if not empty
                if mapped['BillingAddress']:
                    sale['BillingAddress'] = mapped['BillingAddress']
        
        # ShippingAddress - override if explicitly provided
        if 'ShippingAddress' in mapped and mapped['ShippingAddress']:
            try:
                shipping_addr_value = str(uuid.UUID(mapped['ShippingAddress']))
                if shipping_addr_value:  # Only set if not empty
                    sale['ShippingAddress'] = shipping_addr_value
            except ValueError:
                # If not a UUID, might be an address object - pass as-is if not empty
                if mapped['ShippingAddress']:
                    sale['ShippingAddress'] = mapped['ShippingAddress']
        
        # ShipBy - date when order should be shipped
        if 'ShipBy' in mapped and mapped['ShipBy']:
            from cin7_sales.csv_parser import CSVParser
            parser = CSVParser()
            parsed_date = parser._parse_date(mapped['ShipBy'], None)
            if parsed_date:
                sale['ShipBy'] = parsed_date
            else:
                sale['ShipBy'] = mapped['ShipBy']
        
        # CustomerReference (PO number)
        if 'CustomerReference' in mapped and mapped['CustomerReference']:
            sale['CustomerReference'] = mapped['CustomerReference']
        
        return sale
    
    def build_sale_order(self, row_data: Dict[str, Any], column_mapping: Dict[str, str], sale_id: str) -> Dict[str, Any]:
        """
        Build a Cin7 Sale Order payload from CSV row data.
        Sale Order includes: Total, Tax, and references the Sale ID.
        
        Args:
            row_data: Raw CSV row data
            column_mapping: Mapping of Cin7 fields to CSV columns
            sale_id: The ID of the Sale created in the first step
        
        Returns:
            Cin7 Sale Order dictionary
        """
        # Extract mapped values
        mapped = {}
        for cin7_field, csv_column in column_mapping.items():
            if csv_column and csv_column in row_data:
                mapped[cin7_field] = row_data[csv_column]
        
        # Build Sale Order payload - SaleID, Status, and Lines are required
        # Status for POST: only DRAFT and AUTHORISED are accepted
        status = self.settings.get('default_status', 'DRAFT')
        if status not in ['DRAFT', 'AUTHORISED']:
            status = 'DRAFT'  # Default to DRAFT if invalid
        
        sale_order = {
            'SaleID': sale_id,  # Reference to the Sale created first
            'Status': status
        }
        
        # Build lines - required
        lines = self._build_lines(row_data, column_mapping)
        if not lines:
            # If no lines could be built, this is an error condition
            # But we'll return empty lines array and let validation catch it
            lines = []
        sale_order['Lines'] = lines
        
        # Calculate Total from lines (sum of all line totals)
        total = 0.0
        for line in lines:
            quantity = line.get('Quantity', 0)
            price = line.get('Price', 0)
            discount = line.get('Discount', 0)
            line_total = (quantity * price) - discount
            total += line_total
        
        sale_order['Total'] = total
        
        # Tax - can be provided directly or calculated from lines
        tax = 0.0
        if 'Tax' in mapped and mapped['Tax']:
            try:
                tax_str = str(mapped['Tax']).replace('$', '').replace(',', '').strip()
                tax = float(tax_str)
            except (ValueError, TypeError):
                pass
        
        # If tax not provided, calculate from line taxes
        if tax == 0.0 and lines:
            for line in lines:
                line_tax = line.get('Tax', 0.0)
                if isinstance(line_tax, (int, float)):
                    tax += float(line_tax)
        
        sale_order['Tax'] = tax
        
        return sale_order
    
    def _lookup_customer_by_name(self, customer_name: str) -> Optional[Dict[str, Any]]:
        """
        Lookup customer by name and return customer data with shipping/billing IDs.
        
        Args:
            customer_name: Customer name to lookup
        
        Returns:
            Customer data dictionary or None
        """
        if not customer_name:
            return None
        
        # Check cache first
        if customer_name in self._customer_cache:
            return self._customer_cache[customer_name]
        
        # Check preloaded data first (avoid API calls)
        if self.preloaded_customers:
            customer_name_clean = customer_name.strip()
            customer = (self.preloaded_customers.get(customer_name_clean) or 
                       self.preloaded_customers.get(customer_name_clean.upper()) or
                       self.preloaded_customers.get(customer_name_clean.lower()))
            if customer:
                self._customer_cache[customer_name] = customer
                return customer
        
        # Only fallback to API if NOT preloaded (to avoid individual API calls)
        if self.api_client and not self.preloaded_customers:
            customers = self.api_client.search_customer(name=customer_name)
            
            if customers and len(customers) > 0:
                # Use first match
                customer = customers[0]
                self._customer_cache[customer_name] = customer
                return customer
        
        # Cache None to avoid repeated lookups
        self._customer_cache[customer_name] = None
        return None
    
    def _build_lines(self, row_data: Dict[str, Any], column_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """Build sales order lines from row data"""
        lines = []
        
        # Check if Lines is provided as JSON
        if 'Lines' in column_mapping and column_mapping['Lines']:
            lines_col = column_mapping['Lines']
            if lines_col in row_data:
                import json
                try:
                    if isinstance(row_data[lines_col], str):
                        lines_data = json.loads(row_data[lines_col])
                    else:
                        lines_data = row_data[lines_col]
                    
                    if isinstance(lines_data, list):
                        for line in lines_data:
                            if isinstance(line, dict):
                                lines.append(self._build_line(line))
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # If no lines from JSON, try to build from individual columns
        if not lines:
            # Check for line item columns (e.g., SKU_1, Quantity_1, Price_1, etc.)
            line_items = {}
            for key, value in row_data.items():
                if '_' in key:
                    parts = key.rsplit('_', 1)
                    if len(parts) == 2:
                        field_name, line_num = parts
                        try:
                            line_index = int(line_num) - 1  # Convert to 0-based
                            if line_index not in line_items:
                                line_items[line_index] = {}
                            line_items[line_index][field_name] = value
                        except ValueError:
                            pass
            
            # Build lines from line items
            for line_index in sorted(line_items.keys()):
                line_data = line_items[line_index]
                line = self._build_line(line_data)
                if line:
                    lines.append(line)
        
        # If still no lines, try single line from main columns using column mapping
        if not lines:
            # Build line from column mapping
            line = {}
            
            # Check if SKU is provided (Item Code)
            if 'SKU' in column_mapping and column_mapping['SKU']:
                sku_col = column_mapping['SKU']
                if sku_col in row_data:
                    sku = row_data[sku_col]
                    if sku:
                        line['SKU'] = sku
                        
                        # Quantity - may need to calculate from Extended Price / Price
                        quantity = None
                        if 'Quantity' in column_mapping and column_mapping['Quantity']:
                            qty_col = column_mapping['Quantity']
                            if qty_col in row_data:
                                try:
                                    quantity = float(row_data[qty_col])
                                except (ValueError, TypeError):
                                    pass
                        
                        # If no quantity, try to calculate from Extended Price / Price
                        if not quantity:
                            price = None
                            extended_price = None
                            
                            # Get Price
                            if 'Price' in column_mapping and column_mapping['Price']:
                                price_col = column_mapping['Price']
                                if price_col in row_data:
                                    try:
                                        price_str = str(row_data[price_col]).replace('$', '').replace(',', '').strip()
                                        price = float(price_str)
                                    except (ValueError, TypeError):
                                        pass
                            
                            # Check for Extended Price column (common in CSV exports)
                            # Look for common extended price column names
                            for col_name in row_data.keys():
                                if 'extended' in col_name.lower() or 'total' in col_name.lower():
                                    try:
                                        ext_str = str(row_data[col_name]).replace('$', '').replace(',', '').strip()
                                        extended_price = float(ext_str)
                                        break
                                    except (ValueError, TypeError):
                                        pass
                            
                            # Calculate quantity if we have both prices
                            if price and extended_price and price > 0:
                                quantity = extended_price / price
                        
                        if quantity:
                            line['Quantity'] = quantity
                        
                        # Price (required)
                        if 'Price' in column_mapping and column_mapping['Price']:
                            price_col = column_mapping['Price']
                            if price_col in row_data:
                                try:
                                    # Remove currency symbols and parse
                                    price_str = str(row_data[price_col]).replace('$', '').replace(',', '').strip()
                                    line['Price'] = float(price_str)
                                except (ValueError, TypeError):
                                    pass
                        
                        # Lookup product by SKU to get ProductID and Name
                        if sku:
                            product = self._lookup_product_by_sku(sku)
                            if product:
                                product_id = product.get('ID')
                                if product_id:
                                    line['ProductID'] = product_id
                                
                                # Use product name from lookup
                                product_name = product.get('Name')
                                if product_name:
                                    line['Name'] = product_name
                        
                        # If Name not set from product lookup, use from CSV
                        if 'Name' not in line:
                            if 'ProductName' in column_mapping and column_mapping['ProductName']:
                                name_col = column_mapping['ProductName']
                                if name_col in row_data:
                                    line['Name'] = row_data[name_col]
                        
                        # Tax - default to 0
                        line['Tax'] = 0.0
                        
                        # TaxRule - pull from settings
                        tax_rule = self.settings.get('tax_rule')
                        if tax_rule:
                            line['TaxRule'] = tax_rule
                        
                        if line.get('SKU') and line.get('Price'):
                            lines.append(line)
        
        return lines
    
    def _lookup_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Lookup product by SKU and return product data with ID and Name.
        
        Args:
            sku: Product SKU to lookup
        
        Returns:
            Product data dictionary or None
        """
        if not sku:
            return None
        
        # Check cache first
        if sku in self._product_cache:
            return self._product_cache[sku]
        
        # Check preloaded data first (avoid API calls)
        if self.preloaded_products:
            sku_clean = sku.strip()
            product = (self.preloaded_products.get(sku_clean) or 
                      self.preloaded_products.get(sku_clean.upper()) or
                      self.preloaded_products.get(sku_clean.lower()))
            if product:
                self._product_cache[sku] = product
                return product
        
        # Only fallback to API if NOT preloaded (to avoid individual API calls)
        if self.api_client and not self.preloaded_products:
            product = self.api_client.get_product(sku)
            if product:
                self._product_cache[sku] = product
                return product
        
        # Cache None to avoid repeated lookups
        self._product_cache[sku] = None
        return None
    
    def _build_line(self, line_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build a single sales order line.
        Required fields: ProductID, Name, Quantity, Price, Tax, TaxRule
        """
        line = {}
        
        # SKU (required for lookup, but ProductID is what gets sent)
        sku = line_data.get('SKU') or line_data.get('sku') or line_data.get('product_sku')
        if not sku:
            return None
        
        # Lookup product by SKU to get ProductID and Name (both required)
        product = self._lookup_product_by_sku(sku)
        if not product:
            return None  # Cannot build line without product lookup
        
        product_id = product.get('ID')
        if not product_id:
            return None  # ProductID is required
        
        line['ProductID'] = product_id
        
        # Name is required - use from product lookup (from Cin7)
        product_name = product.get('Name')
        if not product_name:
            # Fallback to line_data if product doesn't have name
            product_name = line_data.get('ProductName') or line_data.get('product_name') or line_data.get('name')
            if not product_name:
                return None  # Name is required
        
        line['Name'] = product_name
        
        # Quantity (required)
        quantity = line_data.get('Quantity') or line_data.get('quantity') or line_data.get('qty')
        if quantity:
            try:
                line['Quantity'] = float(quantity)
            except (ValueError, TypeError):
                line['Quantity'] = 1.0
        else:
            line['Quantity'] = 1.0
        
        # Price (required)
        price = line_data.get('Price') or line_data.get('price') or line_data.get('unit_price')
        if not price:
            return None  # Price is required
        
        try:
            price_str = str(price).replace('$', '').replace(',', '').strip()
            line['Price'] = float(price_str)
        except (ValueError, TypeError):
            return None  # Invalid price
        
        # Tax (required, defaults to 0.0)
        tax = line_data.get('Tax') or line_data.get('tax')
        if tax:
            try:
                line['Tax'] = float(tax)
            except (ValueError, TypeError):
                line['Tax'] = 0.0
        else:
            line['Tax'] = 0.0
        
        # TaxRule (required - from settings or use empty string)
        tax_rule = self.settings.get('tax_rule')
        line['TaxRule'] = tax_rule if tax_rule else ''
        
        # Discount (optional)
        discount = line_data.get('Discount') or line_data.get('discount')
        if discount:
            try:
                line['Discount'] = float(discount)
            except (ValueError, TypeError):
                pass
        
        return line



