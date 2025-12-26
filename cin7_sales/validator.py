"""
Validator for Sales Order Data
"""
from typing import List, Dict, Any, Tuple, Optional
from cin7_sales.api_client import Cin7SalesAPI
from cin7_sales.fuzzy_match import fuzzy_match_customer, fuzzy_match_address
import uuid


class SalesOrderValidator:
    """Validator for sales order data before sending to Cin7"""
    
    def __init__(self, api_client: Cin7SalesAPI):
        """
        Initialize the validator.
        
        Args:
            api_client: Cin7SalesAPI instance for validating against Cin7
        """
        self.api_client = api_client
        self.customer_cache = {}  # Cache validated customers (by ID)
        self.product_cache = {}   # Cache validated products (by SKU)
        self.customer_lookup = {}  # Lookup by code/name: {code: customer_data, name: customer_data}
        self.product_lookup = {}    # Lookup by SKU: {sku: product_data}
        self.customers_loaded = False
        self.products_loaded = False
    
    def validate_row(self, row_data: Dict[str, Any], column_mapping: Dict[str, str], 
                    settings: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate a single row of sales order data.
        
        Args:
            row_data: Raw row data from CSV
            column_mapping: Mapping of Cin7 fields to CSV columns
            settings: Client settings (defaults, requirements, etc.)
        
        Returns:
            (is_valid, errors, validation_metadata) - Boolean, list of error messages, and metadata dict
            validation_metadata contains: customer_match, address_match, needs_customer_creation, needs_address_creation
        """
        errors = []
        validation_metadata = {
            'customer_match': None,
            'address_match': None,
            'needs_customer_creation': False,
            'needs_address_creation': False
        }
        
        # Extract mapped values
        mapped_data = {}
        for cin7_field, csv_column in column_mapping.items():
            if csv_column and csv_column in row_data:
                mapped_data[cin7_field] = row_data[csv_column]
        
        # Validate required fields - CustomerName is now the primary way to lookup
        customer_name = mapped_data.get('CustomerName')
        customer_id = mapped_data.get('CustomerID')
        shipping_address_str = mapped_data.get('ShippingAddress')  # Address string from CSV
        
        customer_match_result = None
        address_match_result = None
        needs_customer_creation = False
        needs_address_creation = False
        
        if customer_name:
            # First try exact lookup
            customer = None
            if self.customers_loaded:
                # Get all customer candidates for fuzzy matching
                customer_candidates = []
                for key, cust in self.customer_lookup.items():
                    if isinstance(cust, dict) and cust.get('Name'):
                        # Avoid duplicates (same customer may be stored multiple ways)
                        if cust not in customer_candidates:
                            customer_candidates.append(cust)
                
                # Try fuzzy matching if we have candidates
                if customer_candidates:
                    customer_match_result = fuzzy_match_customer(customer_name, customer_candidates, threshold=0.85)
                    if customer_match_result[0]:  # Found a match above threshold
                        customer = customer_match_result[0]
                    else:
                        # No fuzzy match found - will need to create customer
                        needs_customer_creation = True
                else:
                    # No customers loaded - will need to create
                    needs_customer_creation = True
            else:
                # Not preloaded - try API search
                customers = self.api_client.search_customer(name=customer_name)
                if customers and len(customers) > 0:
                    # Use fuzzy matching on API results
                    customer_match_result = fuzzy_match_customer(customer_name, customers, threshold=0.85)
                    if customer_match_result[0]:
                        customer = customer_match_result[0]
                    elif len(customers) == 1:
                        # Single result, use it even if below threshold
                        customer = customers[0]
                    else:
                        # Multiple results but none match well - flag for creation
                        needs_customer_creation = True
                else:
                    # No customers found - will need to create
                    needs_customer_creation = True
            
            # If we have a customer, try to match shipping address
            if customer and shipping_address_str:
                # Get customer's addresses
                customer_addresses = []
                
                # Check ShippingAddress
                shipping_addr = customer.get('ShippingAddress')
                if shipping_addr:
                    if isinstance(shipping_addr, dict):
                        customer_addresses.append(shipping_addr)
                    elif isinstance(shipping_addr, list):
                        customer_addresses.extend(shipping_addr)
                
                # Check BillingAddress (sometimes used as shipping)
                billing_addr = customer.get('BillingAddress')
                if billing_addr:
                    if isinstance(billing_addr, dict):
                        if billing_addr not in customer_addresses:
                            customer_addresses.append(billing_addr)
                    elif isinstance(billing_addr, list):
                        for addr in billing_addr:
                            if addr not in customer_addresses:
                                customer_addresses.append(addr)
                
                # Try fuzzy matching on addresses
                if customer_addresses:
                    address_match_result = fuzzy_match_address(shipping_address_str, customer_addresses, threshold=0.80)
                    if not address_match_result[0]:  # No good match found
                        needs_address_creation = True
                else:
                    # Customer has no addresses - will need to create one
                    needs_address_creation = True
            
            if not customer and not needs_customer_creation:
                errors.append(f"Customer '{customer_name}' not found in Cin7")
            elif needs_customer_creation:
                # Store in metadata - customer will be created
                validation_metadata['needs_customer_creation'] = True
                validation_metadata['customer_name_to_create'] = customer_name
            
            # Store match results in metadata (store IDs only, not full objects for serialization)
            if customer_match_result:
                matched_customer = customer if 'customer' in locals() and customer else customer_match_result[0]
                validation_metadata['customer_match'] = {
                    'customer_id': str(matched_customer.get('ID')) if matched_customer and matched_customer.get('ID') else None,
                    'customer_name': matched_customer.get('Name') if matched_customer else None,
                    'match_score': customer_match_result[1],
                    'all_matches': [
                        {'name': m[0].get('Name'), 'id': str(m[0].get('ID')), 'score': m[1]}
                        for m in customer_match_result[2][:5]  # Top 5 matches
                        if m[0].get('ID')  # Only include matches with IDs
                    ]
                }
            
            if address_match_result:
                matched_address = address_match_result[0]
                validation_metadata['address_match'] = {
                    'address_id': str(matched_address.get('ID')) if matched_address and matched_address.get('ID') else None,
                    'match_score': address_match_result[1],
                    'all_matches': [
                        {'address_id': str(m[0].get('ID')), 'score': m[1]}
                        for m in address_match_result[2][:3]  # Top 3 matches
                        if m[0].get('ID')  # Only include matches with IDs
                    ]
                }
            
            if needs_address_creation:
                validation_metadata['needs_address_creation'] = True
                validation_metadata['address_to_create'] = shipping_address_str
        elif customer_id:
            is_valid, message = self.validate_customer_id(customer_id)
            if not is_valid:
                errors.append(f"Customer validation failed: {message}")
        else:
            errors.append("CustomerName or CustomerID is required")
        
        # Validate sale date - try to parse it
        sale_date = mapped_data.get('SaleDate')
        if sale_date:
            from datetime import datetime
            from cin7_sales.csv_parser import CSVParser
            parser = CSVParser()
            parsed_date = parser._parse_date(sale_date, None)
            if not parsed_date:
                errors.append(f"Invalid date format for SaleDate: {sale_date}. Could not parse date")
        
        # Validate currency
        currency = mapped_data.get('Currency', settings.get('default_currency', 'USD'))
        if currency and len(currency) != 3:
            errors.append(f"Invalid currency code: {currency}. Must be 3 characters (e.g., USD)")
        
        # Location is not validated - it's optional and will default with the customer if not provided
        
        # Validate lines (if provided as JSON string)
        lines = mapped_data.get('Lines')
        if lines:
            try:
                import json
                if isinstance(lines, str):
                    lines_data = json.loads(lines)
                else:
                    lines_data = lines
                
                if not isinstance(lines_data, list):
                    errors.append("Lines must be a list/array")
                else:
                    # Validate each line
                    for i, line in enumerate(lines_data):
                        if not isinstance(line, dict):
                            errors.append(f"Line {i+1} must be an object")
                            continue
                        
                        if 'SKU' not in line:
                            errors.append(f"Line {i+1} missing SKU (Item Code)")
                        
                        # Quantity is optional - may be calculated from Extended Price / Price
                        if 'Quantity' in line:
                            try:
                                qty = float(line['Quantity'])
                                if qty <= 0:
                                    errors.append(f"Line {i+1} Quantity must be greater than 0")
                            except (ValueError, TypeError):
                                errors.append(f"Line {i+1} Quantity must be a number")
                        
                        # Price is required for line items
                        if 'Price' not in line:
                            errors.append(f"Line {i+1} missing Price")
                        else:
                            try:
                                price = float(line['Price'])
                                if price < 0:
                                    errors.append(f"Line {i+1} Price cannot be negative")
                            except (ValueError, TypeError):
                                errors.append(f"Line {i+1} Price must be a number")
                        
                        # Validate product exists by SKU
                        if 'SKU' in line:
                            sku = line['SKU']
                            is_valid, message, product_id = self.validate_product_sku(sku)
                            if not is_valid:
                                errors.append(f"Line {i+1} product validation failed: {message}")
            except json.JSONDecodeError:
                errors.append("Lines must be valid JSON")
        
        # Check requirements from settings
        if settings.get('require_customer_reference') and not mapped_data.get('CustomerReference'):
            errors.append("CustomerReference is required")
        
        if settings.get('require_invoice_number') and not mapped_data.get('InvoiceNumber'):
            errors.append("InvoiceNumber is required")
        
        return len(errors) == 0, errors, validation_metadata
    
    def validate_customer_id(self, customer_id: str) -> Tuple[bool, str]:
        """
        Validate that a customer ID exists in Cin7.
        
        Args:
            customer_id: Customer ID to validate
        
        Returns:
            (is_valid, message)
        """
        # Check cache first
        if customer_id in self.customer_cache:
            cached_result = self.customer_cache[customer_id]
            return cached_result['valid'], cached_result['message']
        
        # Check preloaded lookup if available (avoid API call)
        if self.customers_loaded and customer_id in self.customer_lookup:
            result = (True, "Customer exists")
            self.customer_cache[customer_id] = {'valid': True, 'message': 'Customer exists'}
            return result
        
        # Validate UUID format
        try:
            uuid.UUID(customer_id)
        except ValueError:
            result = (False, "Invalid UUID format")
            self.customer_cache[customer_id] = {'valid': False, 'message': result[1]}
            return result
        
        # Only check with API if NOT preloaded (to avoid individual API calls)
        if not self.customers_loaded:
            is_valid, message = self.api_client.validate_customer(customer_id)
            self.customer_cache[customer_id] = {'valid': is_valid, 'message': message}
            return is_valid, message
        else:
            # Preloaded but customer not found
            result = (False, "Customer not found")
            self.customer_cache[customer_id] = {'valid': False, 'message': 'Customer not found'}
            return result
    
    def validate_product_sku(self, sku: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate that a product SKU exists in Cin7.
        
        Args:
            sku: Product SKU to validate
        
        Returns:
            (is_valid, message, product_id)
        """
        # Check cache first
        if sku in self.product_cache:
            cached_result = self.product_cache[sku]
            return cached_result['valid'], cached_result['message'], cached_result.get('product_id')
        
        # Check preloaded lookup first (strip whitespace)
        if self.products_loaded:
            sku_clean = sku.strip() if sku else None
            product = (self.product_lookup.get(sku_clean) or 
                      self.product_lookup.get(sku_clean.upper()) if sku_clean else None)
            if product:
                product_id = product.get("ID")
                result = (True, "Product exists", product_id)
                self.product_cache[sku] = {
                    'valid': True,
                    'message': 'Product exists',
                    'product_id': product_id
                }
                return result
            else:
                # Product not found in preloaded data - mark as not found (no API call)
                result = (False, "Product not found", None)
                self.product_cache[sku] = {
                    'valid': False,
                    'message': 'Product not found',
                    'product_id': None
                }
                return result
        
        # Only fallback to API if NOT preloaded (to avoid individual API calls)
        is_valid, message, product_id = self.api_client.validate_product(sku)
        self.product_cache[sku] = {
            'valid': is_valid,
            'message': message,
            'product_id': product_id
        }
        return is_valid, message, product_id
    
    def _get_field_status(self, cin7_field: str, mapped_value: Any, is_required: bool, 
                          column_mapping: Dict[str, str], row_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get status information for a Cin7 field.
        
        Returns:
            Dictionary with 'status' ('ready', 'missing', 'invalid'), 'value', 'source', 'message'
        """
        csv_column = column_mapping.get(cin7_field)
        
        # Check if field is mapped
        if not csv_column:
            return {
                'status': 'missing' if is_required else 'optional',
                'value': None,
                'source': None,
                'message': 'Not mapped' + (' (required)' if is_required else ' (optional)')
            }
        
        # Get value from CSV
        if csv_column and csv_column in row_data:
            raw_value = row_data.get(csv_column, '')
            value = raw_value.strip() if raw_value and isinstance(raw_value, str) else (raw_value if raw_value else None)
        else:
            value = None
        
        # Check if value exists
        if not value:
            # Check if there's a default from settings
            if cin7_field == 'Currency' and not value:
                return {
                    'status': 'ready',
                    'value': 'USD',
                    'source': 'default',
                    'message': 'Using default currency'
                }
            return {
                'status': 'missing' if is_required else 'optional',
                'value': None,
                'source': csv_column,
                'message': 'Empty value' + (' (required)' if is_required else ' (optional)')
            }
        
        # Value exists - check if it's valid
        # Basic validation based on field type
        if cin7_field == 'SaleDate' and value:
            from cin7_sales.csv_parser import CSVParser
            parser = CSVParser()
            parsed_date = parser._parse_date(value, None)
            if not parsed_date:
                return {
                    'status': 'invalid',
                    'value': value,
                    'source': csv_column,
                    'message': f'Invalid date format: {value}'
                }
            return {
                'status': 'ready',
                'value': parsed_date,
                'source': csv_column,
                'message': 'Date parsed successfully'
            }
        
        # For other fields, if value exists, it's ready
        return {
            'status': 'ready',
            'value': value,
            'source': csv_column,
            'message': 'Mapped and ready'
        }
    
    def _group_rows_by_order(self, rows: List[Dict[str, Any]], column_mapping: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group rows by Invoice # or Sales Order #.
        
        Returns:
            Dictionary mapping order_key -> list of rows in that order
        """
        groups = {}
        
        # Find InvoiceNumber or SaleOrderNumber column
        invoice_col = column_mapping.get('InvoiceNumber')
        sale_order_col = column_mapping.get('SaleOrderNumber')
        
        # Debug: Log column mapping for troubleshooting
        if rows and invoice_col:
            # Check if invoice column exists in first row's data
            first_row_cols = list(rows[0]['data'].keys())
            if invoice_col not in first_row_cols:
                # Try case-insensitive match
                matching_col = None
                for col in first_row_cols:
                    if col.lower() == invoice_col.lower():
                        matching_col = col
                        break
                if matching_col:
                    invoice_col = matching_col  # Update to use the actual column name
        
        for row in rows:
            order_key = None
            
            # Try Invoice # first - handle both exact match and case-insensitive match
            if invoice_col:
                invoice_val = None
                # Try exact match first
                if invoice_col in row['data']:
                    invoice_val = row['data'][invoice_col]
                else:
                    # Try case-insensitive match
                    for key, val in row['data'].items():
                        if key.lower() == invoice_col.lower():
                            invoice_val = val
                            break
                
                if invoice_val and str(invoice_val).strip():
                    order_key = f"INV_{str(invoice_val).strip()}"
            
            # Fallback to Sales Order # - handle both exact match and case-insensitive match
            if not order_key and sale_order_col:
                so_val = None
                if sale_order_col in row['data']:
                    so_val = row['data'][sale_order_col]
                else:
                    # Try case-insensitive match
                    for key, val in row['data'].items():
                        if key.lower() == sale_order_col.lower():
                            so_val = val
                            break
                if so_val and str(so_val).strip():
                    order_key = f"SO_{str(so_val).strip()}"
            
            # If no grouping key found, treat each row as its own order
            if not order_key:
                order_key = f"ROW_{row['row_number']}"
            
            if order_key not in groups:
                groups[order_key] = []
            groups[order_key].append(row)
        
        return groups
    
    def validate_batch(self, rows: List[Dict[str, Any]], column_mapping: Dict[str, str],
                      settings: Dict[str, Any], builder=None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate a batch of rows. Groups rows by Invoice # or Sales Order #.
        
        Args:
            rows: List of row dictionaries with 'row_number' and 'data'
            column_mapping: Mapping of Cin7 fields to CSV columns
            settings: Client settings
            builder: Optional SalesOrderBuilder to generate preview payloads
        
        Returns:
            (valid_rows, invalid_rows) - Lists of row dictionaries with validation results
        """
        valid_rows = []
        invalid_rows = []
        
        # Group rows by Invoice # or Sales Order #
        row_groups = self._group_rows_by_order(rows, column_mapping)
        
        # Define required fields
        required_fields = ['CustomerName', 'CustomerReference', 'SaleDate', 'SKU', 'Price']
        optional_fields = ['Currency', 'TaxInclusive', 'ProductName', 'Quantity', 'Discount', 'Tax', 'Notes']
        
        # Process each group (order)
        for order_key, group_rows in row_groups.items():
            # Use the first row as the primary row for order-level data
            primary_row = group_rows[0]
            
            # Build mapped data from primary row
            mapped_data = {}
            for cin7_field, csv_column in column_mapping.items():
                if csv_column and csv_column in primary_row['data']:
                    mapped_data[cin7_field] = primary_row['data'][csv_column]
            
            # Validate each row in the group (for individual line item validation)
            group_errors = []
            group_validation_metadata = {}
            all_row_numbers = [r['row_number'] for r in group_rows]
            
            for row in group_rows:
                is_valid, errors, validation_metadata = self.validate_row(row['data'], column_mapping, settings)
                group_errors.extend(errors)
                # Merge validation metadata (use first non-empty customer/address match)
                if validation_metadata.get('customer_match') and not group_validation_metadata.get('customer_match'):
                    group_validation_metadata['customer_match'] = validation_metadata['customer_match']
                if validation_metadata.get('address_match') and not group_validation_metadata.get('address_match'):
                    group_validation_metadata['address_match'] = validation_metadata['address_match']
                if validation_metadata.get('needs_customer_creation'):
                    group_validation_metadata['needs_customer_creation'] = True
                if validation_metadata.get('needs_address_creation'):
                    group_validation_metadata['needs_address_creation'] = True
            
            # Build field status information
            field_status = {}
            all_fields = required_fields + optional_fields
            
            for field in all_fields:
                is_required = field in required_fields
                field_status[field] = self._get_field_status(
                    field, mapped_data.get(field), is_required, column_mapping, primary_row['data']
                )
                
                # Override status based on validation metadata (fuzzy matching results)
                if field == 'CustomerName' and mapped_data.get('CustomerName'):
                    # Check validation metadata for fuzzy matching results
                    if group_validation_metadata.get('needs_customer_creation'):
                        field_status[field]['status'] = 'warning'
                        field_status[field]['message'] = f"Customer '{mapped_data.get('CustomerName')}' not found - will be created during order processing"
                    elif group_validation_metadata.get('customer_match') and group_validation_metadata['customer_match'].get('customer_id'):
                        customer_match = group_validation_metadata['customer_match']
                        match_score = customer_match.get('match_score', 1.0)
                        if match_score < 1.0:
                            field_status[field]['status'] = 'ready'
                            field_status[field]['message'] = f"Fuzzy matched customer ({(match_score*100):.0f}% match)"
                        else:
                            field_status[field]['status'] = 'ready'
                            field_status[field]['message'] = 'Customer found in Cin7 (exact match)'
                    else:
                        customer_errors = [e for e in group_errors if 'Customer' in e and ('not found' in e.lower() or 'Customer validation failed' in e)]
                        if customer_errors:
                            field_status[field]['status'] = 'invalid'
                            field_status[field]['message'] = customer_errors[0]
                        elif field_status[field]['status'] == 'ready':
                            field_status[field]['message'] = 'Customer found in Cin7'
                
                if field == 'ShippingAddress' and mapped_data.get('ShippingAddress'):
                    # Check address matching results
                    if group_validation_metadata.get('needs_address_creation'):
                        field_status[field]['status'] = 'warning'
                        field_status[field]['message'] = "Address not found for customer - will be created during order processing"
                    elif group_validation_metadata.get('address_match') and group_validation_metadata['address_match'].get('address'):
                        address_match = group_validation_metadata['address_match']
                        match_score = address_match.get('match_score', 1.0)
                        if match_score < 1.0:
                            field_status[field]['status'] = 'ready'
                            field_status[field]['message'] = f"Fuzzy matched address ({(match_score*100):.0f}% match)"
                        else:
                            field_status[field]['status'] = 'ready'
                            field_status[field]['message'] = 'Address found for customer (exact match)'
            
            # Build preview payloads if builder is available
            preview_payloads = None
            if builder:
                try:
                    # Build sale from primary row
                    sale_payload = builder.build_sale(primary_row['data'], column_mapping)
                    
                    # Build sale order with all line items from all rows in the group
                    row_data_list = [r['data'] for r in group_rows]
                    sale_order_payload = builder.build_sale_order_from_rows(row_data_list, column_mapping, 'PLACEHOLDER_SALE_ID')
                    
                    preview_payloads = {
                        'sale': sale_payload,
                        'sale_order': sale_order_payload
                    }
                    
                    # Fix Price field status by checking if price exists in the preview payload lines
                    if field_status.get('Price') and field_status['Price']['status'] != 'ready':
                        # Check if any line in the sale order has a price
                        lines = sale_order_payload.get('Lines', [])
                        has_price = any(line.get('Price') for line in lines)
                        if has_price:
                            field_status['Price']['status'] = 'ready'
                            field_status['Price']['message'] = 'Price calculated from Total ÷ Quantity'
                            # Set value from first line with price
                            for line in lines:
                                if line.get('Price'):
                                    field_status['Price']['value'] = line.get('Price')
                                    break
                    
                    # Add customer creation preview if needed
                    if group_validation_metadata.get('needs_customer_creation'):
                        customer_name = mapped_data.get('CustomerName')
                        if customer_name:
                            # Build customer creation payload with required and default fields
                            customer_payload = {
                                'Name': customer_name,
                                'Status': 'Active',
                                'Currency': 'USD'
                            }
                            
                            # Add default fields from settings if available
                            if settings.get('customer_account_receivable'):
                                customer_payload['AccountReceivable'] = settings['customer_account_receivable']
                            if settings.get('customer_revenue_account'):
                                customer_payload['RevenueAccount'] = settings['customer_revenue_account']
                            if settings.get('customer_tax_rule'):
                                customer_payload['TaxRule'] = settings['customer_tax_rule']
                            if settings.get('customer_attribute_set'):
                                customer_payload['AttributeSet'] = settings['customer_attribute_set']
                            
                            # Add AdditionalAttribute1 from CSV if mapped
                            if 'AdditionalAttribute1' in column_mapping and column_mapping['AdditionalAttribute1']:
                                attr_col = column_mapping['AdditionalAttribute1']
                                if attr_col in primary_row['data']:
                                    attr_value = primary_row['data'][attr_col]
                                    if attr_value and str(attr_value).strip():
                                        customer_payload['AdditionalAttribute1'] = str(attr_value).strip()
                            
                            preview_payloads['customer_creation'] = customer_payload
                            
                            # Update sale payload to show it will reference the newly created customer by ID
                            # The sale will use CustomerID from the created customer response
                            if sale_payload:
                                # Remove Customer field and set CustomerID to show it will use the created customer's ID
                                sale_payload['CustomerID'] = '<CREATED_CUSTOMER_ID>'  # Placeholder to show it will be set
                                sale_payload['Customer'] = customer_name  # Include customer name
                                sale_payload['_note'] = 'CustomerID will be set from created customer response. Customer will be created first, then Sale will reference the returned CustomerID.'
                except Exception as e:
                    preview_payloads = {'error': f'Failed to build payloads: {str(e)}'}
            
            # Calculate order metrics from preview payload
            po_number = mapped_data.get('CustomerReference', '')
            customer_name = mapped_data.get('CustomerName', '')
            order_date = mapped_data.get('SaleDate', '')
            due_date = mapped_data.get('ShipBy', '')
            line_item_count = 0
            total_cases = 0.0
            order_total = 0.0
            
            if preview_payloads and not preview_payloads.get('error'):
                sale_order_payload = preview_payloads.get('sale_order')
                if sale_order_payload and 'Lines' in sale_order_payload:
                    lines = sale_order_payload['Lines']
                    line_item_count = len(lines)
                    # Sum quantities (cases) from all lines
                    for line in lines:
                        quantity = line.get('Quantity', 0)
                        if quantity:
                            try:
                                total_cases += float(quantity)
                            except (ValueError, TypeError):
                                pass
                    # Get order total
                    order_total = sale_order_payload.get('Total', 0.0)
            
            # Determine if group is valid (no critical errors)
            is_group_valid = len([e for e in group_errors if 'required' in e.lower() or 'missing' in e.lower()]) == 0
            
            row_result = {
                'row_numbers': all_row_numbers,  # All row numbers in this group
                'row_number': all_row_numbers[0],  # Primary row number for compatibility
                'data': primary_row['data'],  # Primary row data
                'group_rows': [r['data'] for r in group_rows],  # All row data in group
                'mapped_data': mapped_data,
                'field_status': field_status,
                'preview_payload': preview_payloads,
                'errors': group_errors,
                'valid': is_group_valid,
                'validation_metadata': group_validation_metadata,
                # Order summary metrics
                'po_number': po_number,
                'customer_name': customer_name,
                'order_date': order_date,
                'due_date': due_date,
                'line_item_count': line_item_count,
                'total_cases': total_cases,
                'order_total': order_total
            }
            
            if is_group_valid:
                valid_rows.append(row_result)
            else:
                invalid_rows.append(row_result)
        
        return valid_rows, invalid_rows
    
    def clear_cache(self):
        """Clear validation caches"""
        self.customer_cache.clear()
        self.product_cache.clear()
        self.customer_lookup.clear()
        self.product_lookup.clear()
        self.customers_loaded = False
        self.products_loaded = False
    
    def preload_customers_and_products(self) -> Tuple[int, int]:
        """
        Preload all customers and products from Cin7 for faster validation.
        
        Returns:
            (customer_count, product_count) - Number of customers and products loaded
        """
        customer_count = 0
        product_count = 0
        
        # Load customers
        try:
            customers = self.api_client.get_all_customers()
            customer_count = len(customers)
            
            # Build lookup dictionaries
            for customer in customers:
                customer_id = customer.get("ID")
                customer_name = customer.get("Name")
                
                if customer_id:
                    self.customer_cache[customer_id] = {
                        'valid': True,
                        'message': 'Customer exists',
                        'data': customer
                    }
                    # Also store in lookup by ID for builder convenience
                    self.customer_lookup[customer_id] = customer
                
                # Build lookup by name (case-insensitive, strip whitespace)
                if customer_name:
                    customer_name_clean = customer_name.strip() if customer_name else None
                    if not customer_name_clean:
                        continue
                    # Store by original, upper, and lower case for flexible lookup
                    self.customer_lookup[customer_name_clean] = customer
                    self.customer_lookup[customer_name_clean.upper()] = customer
                    self.customer_lookup[customer_name_clean.lower()] = customer
            
            self.customers_loaded = True
        except Exception as e:
            print(f"Error preloading customers: {str(e)}")
        
        # Load products
        try:
            products = self.api_client.get_all_products()
            product_count = len(products)
            
            # Build lookup dictionary by SKU (strip whitespace for consistent lookup)
            for product in products:
                sku = product.get("SKU")
                product_id = product.get("ID")
                
                if sku:
                    sku_clean = sku.strip()
                    # Store by original, upper, and lower case for flexible lookup
                    self.product_lookup[sku_clean] = product
                    self.product_lookup[sku_clean.upper()] = product
                    self.product_lookup[sku_clean.lower()] = product
                    self.product_cache[sku_clean] = {
                        'valid': True,
                        'message': 'Product exists',
                        'product_id': product_id,
                        'data': product
                    }
            
            self.products_loaded = True
        except Exception as e:
            print(f"Error preloading products: {str(e)}")
        
        return customer_count, product_count



