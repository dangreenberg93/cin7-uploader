"""
Validator for Sales Order Data
"""
from typing import List, Dict, Any, Tuple, Optional
from cin7_sales.api_client import Cin7SalesAPI
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
                    settings: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a single row of sales order data.
        
        Args:
            row_data: Raw row data from CSV
            column_mapping: Mapping of Cin7 fields to CSV columns
            settings: Client settings (defaults, requirements, etc.)
        
        Returns:
            (is_valid, errors) - Boolean and list of error messages
        """
        errors = []
        
        # Extract mapped values
        mapped_data = {}
        for cin7_field, csv_column in column_mapping.items():
            if csv_column and csv_column in row_data:
                mapped_data[cin7_field] = row_data[csv_column]
        
        # Validate required fields - CustomerName is now the primary way to lookup
        customer_name = mapped_data.get('CustomerName')
        customer_id = mapped_data.get('CustomerID')
        
        if customer_name:
            # First check preloaded lookup
            customer = None
            if self.customers_loaded:
                # Strip whitespace and try multiple variations
                customer_name_clean = customer_name.strip()
                customer = (self.customer_lookup.get(customer_name_clean) or 
                           self.customer_lookup.get(customer_name_clean.upper()) or
                           self.customer_lookup.get(customer_name_clean.lower()))
            
            # Only fallback to API search if NOT preloaded (to avoid individual API calls)
            if not customer and not self.customers_loaded:
                customers = self.api_client.search_customer(name=customer_name)
                if customers and len(customers) > 0:
                    customer = customers[0]
                    if len(customers) > 1:
                        errors.append(f"Multiple customers found with name '{customer_name}' - please use CustomerID")
            
            if not customer:
                errors.append(f"Customer '{customer_name}' not found in Cin7")
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
        
        # Validate location (if provided)
        location = mapped_data.get('Location')
        if location:
            try:
                uuid.UUID(location)
            except ValueError:
                errors.append(f"Invalid location UUID: {location}")
        
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
        
        return len(errors) == 0, errors
    
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
        value = row_data.get(csv_column, '').strip() if csv_column in row_data else None
        
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
    
    def validate_batch(self, rows: List[Dict[str, Any]], column_mapping: Dict[str, str],
                      settings: Dict[str, Any], builder=None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate a batch of rows.
        
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
        
        # Define required fields
        required_fields = ['CustomerName', 'CustomerReference', 'SaleDate', 'SKU', 'Price']
        optional_fields = ['Currency', 'TaxInclusive', 'ProductName', 'Quantity', 'Discount', 'Tax', 'Notes']
        
        for row in rows:
            # Build mapped data first
            mapped_data = {}
            for cin7_field, csv_column in column_mapping.items():
                if csv_column and csv_column in row['data']:
                    mapped_data[cin7_field] = row['data'][csv_column]
            
            # Validate the row (this also checks customer/product existence)
            is_valid, errors = self.validate_row(row['data'], column_mapping, settings)
            
            # Build field status information
            field_status = {}
            all_fields = required_fields + optional_fields
            
            for field in all_fields:
                is_required = field in required_fields
                field_status[field] = self._get_field_status(
                    field, mapped_data.get(field), is_required, column_mapping, row['data']
                )
                
                # Override status based on validation errors
                if field == 'CustomerName' and mapped_data.get('CustomerName'):
                    # Check if customer validation failed
                    customer_errors = [e for e in errors if 'Customer' in e and 'not found' in e]
                    if customer_errors:
                        field_status[field]['status'] = 'invalid'
                        field_status[field]['message'] = customer_errors[0]
                    elif field_status[field]['status'] == 'ready':
                        # Customer exists and is valid
                        field_status[field]['message'] = 'Customer found in Cin7'
                
                if field == 'SKU' and mapped_data.get('SKU'):
                    # Check if product validation failed
                    product_errors = [e for e in errors if 'product' in e.lower() and ('not found' in e.lower() or 'validation failed' in e.lower())]
                    if product_errors:
                        field_status[field]['status'] = 'invalid'
                        field_status[field]['message'] = product_errors[0]
                    elif field_status[field]['status'] == 'ready':
                        field_status[field]['message'] = 'Product found in Cin7'
            
            # Build preview payloads if builder is available
            preview_payloads = None
            if builder:
                try:
                    sale_payload = builder.build_sale(row['data'], column_mapping)
                    # Build Sale Order preview with placeholder Sale ID
                    sale_order_payload = builder.build_sale_order(row['data'], column_mapping, 'PLACEHOLDER_SALE_ID')
                    preview_payloads = {
                        'sale': sale_payload,
                        'sale_order': sale_order_payload
                    }
                except Exception as e:
                    preview_payloads = {'error': f'Failed to build payloads: {str(e)}'}
            
            row_result = {
                'row_number': row['row_number'],
                'data': row['data'],
                'mapped_data': mapped_data,
                'field_status': field_status,  # New: detailed field status
                'preview_payload': preview_payloads,  # New: actual JSON payloads that will be sent (Sale and Sale Order)
                'errors': errors,
                'valid': is_valid
            }
            
            if is_valid:
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
                    customer_name_clean = customer_name.strip()
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



