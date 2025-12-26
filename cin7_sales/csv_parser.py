"""
CSV Parser for Sales Orders
"""
import csv
import io
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re


class CSVParser:
    """Parser for CSV files containing sales order data"""
    
    def __init__(self, date_format: str = 'YYYY-MM-DD'):
        """
        Initialize the CSV parser.
        
        Args:
            date_format: Date format string (e.g., 'YYYY-MM-DD', 'MM/DD/YYYY')
        """
        self.date_format = date_format
    
    def _is_row_complete(self, row_data: Dict[str, Any]) -> bool:
        """
        Check if a row is complete (not a summary/total row).
        
        A row is considered incomplete if it's missing key required fields.
        Typically, total/summary rows have mostly empty values except for totals.
        
        Args:
            row_data: Dictionary of row data
        
        Returns:
            True if row appears complete, False if it's likely a summary/total row
        """
        # Count non-empty values
        non_empty_count = sum(1 for v in row_data.values() if v and str(v).strip())
        
        # If row has very few non-empty values (less than 3), it's likely incomplete
        if non_empty_count < 3:
            return False
        
        # Check for key fields that indicate a valid data row
        # Common field names that should be present in a valid row
        key_field_patterns = [
            'customer', 'customer name', 'customername',
            'item', 'item code', 'itemcode', 'sku',
            'order', 'order #', 'order#',
            'date', 'po', 'po #', 'po#'
        ]
        
        row_keys_lower = [k.lower().strip() for k in row_data.keys()]
        row_values_lower = [str(v).lower().strip() for v in row_data.values() if v]
        
        # Check if any key field has a value
        has_key_field = False
        for pattern in key_field_patterns:
            # Check if pattern matches any column name
            if any(pattern in key for key in row_keys_lower):
                # Check if that column has a value
                for key, value in row_data.items():
                    if pattern in key.lower() and value and str(value).strip():
                        has_key_field = True
                        break
                if has_key_field:
                    break
        
        # If no key fields have values, it's likely a summary row
        if not has_key_field:
            return False
        
        # Additional check: if row only has numeric/total fields (like "Extended Price"), it's likely a total row
        total_field_patterns = ['total', 'sum', 'extended price', 'extendedprice', 'amount', 'subtotal']
        has_only_totals = True
        for key, value in row_data.items():
            if value and str(value).strip():
                key_lower = key.lower()
                # If this field is not a total field and has a value, row might be valid
                if not any(pattern in key_lower for pattern in total_field_patterns):
                    has_only_totals = False
                    break
        
        # If row only contains total fields, it's incomplete
        if has_only_totals and non_empty_count <= 2:
            return False
        
        return True
    
    def parse_file(self, file_content: bytes, filename: str = '') -> Tuple[List[Dict[str, Any]], List[str], List[int]]:
        """
        Parse a CSV file and return rows as dictionaries.
        
        Args:
            file_content: CSV file content as bytes
            filename: Optional filename for error messages
        
        Returns:
            (rows, errors, skipped_rows) - List of row dictionaries, list of error messages, and list of skipped row numbers
        """
        errors = []
        rows = []
        skipped_rows = []
        
        try:
            # Try to detect encoding
            content_str = file_content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                content_str = file_content.decode('latin-1')
            except UnicodeDecodeError:
                errors.append(f"Could not decode file {filename}. Please ensure it's UTF-8 or Latin-1 encoded.")
                return rows, errors
        
        # Parse CSV
        try:
            # Try to detect delimiter
            sniffer = csv.Sniffer()
            sample = content_str[:1024]
            delimiter = sniffer.sniff(sample).delimiter
        except:
            delimiter = ','
        
        try:
            reader = csv.DictReader(io.StringIO(content_str), delimiter=delimiter)
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (row 1 is header)
                # Clean up row (remove None values, strip strings)
                cleaned_row = {}
                for key, value in row.items():
                    if key:
                        cleaned_key = key.strip()
                        if value:
                            cleaned_row[cleaned_key] = value.strip()
                        else:
                            cleaned_row[cleaned_key] = ''
                
                if cleaned_row:  # Only process non-empty rows
                    # Check if row is complete (not a summary/total row)
                    if self._is_row_complete(cleaned_row):
                        rows.append({
                            'row_number': row_num,
                            'data': cleaned_row
                        })
                    else:
                        skipped_rows.append(row_num)
        except Exception as e:
            errors.append(f"Error parsing CSV: {str(e)}")
        
        return rows, errors, skipped_rows
    
    def detect_columns(self, rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Detect potential column mappings by analyzing CSV data.
        
        Args:
            rows: List of parsed row dictionaries
        
        Returns:
            Dictionary mapping Cin7 field names to potential CSV column names
        """
        if not rows:
            return {}
        
        # Get all unique column names from the CSV
        all_columns = set()
        for row in rows:
            all_columns.update(row['data'].keys())
        
        all_columns = list(all_columns)
        
        # Common field mappings (case-insensitive matching)
        field_mappings = {
            'CustomerID': ['customer_id', 'customerid', 'customer', 'customer id', 'cust_id'],
            'CustomerName': ['customer_name', 'customername', 'customer name', 'name', 'customer'],
            'CustomerEmail': ['customer_email', 'customeremail', 'customer email', 'email'],
            'SaleOrderNumber': ['sale_order_number', 'saleordernumber', 'sale order number', 'order_number', 'order number', 'order', 'order_id', 'orderid'],
            'InvoiceNumber': ['invoice_number', 'invoicenumber', 'invoice number', 'invoice #', 'invoice#', 'invoice', 'invoice_id', 'invoiceid'],
            'CustomerReference': ['customer_reference', 'customerreference', 'customer reference', 'reference', 'ref', 'po_number', 'po number', 'po'],
            'SaleDate': ['sale_date', 'saledate', 'sale date', 'date', 'order_date', 'order date'],
            'Status': ['status', 'order_status', 'order status'],
            'Location': ['location', 'warehouse', 'location_id', 'locationid'],
            'Currency': ['currency', 'currency_code', 'currencycode'],
            'TaxInclusive': ['tax_inclusive', 'taxinclusive', 'tax inclusive', 'tax_inc'],
            'Lines': ['lines', 'items', 'products', 'line_items'],
            'SKU': ['sku', 'product_sku', 'productsku', 'product sku', 'item_sku', 'itemsku'],
            'ProductName': ['product_name', 'productname', 'product name', 'name', 'item_name', 'itemname'],
            'Quantity': ['quantity', 'qty', 'qty_ordered', 'qtyordered'],
            'Price': ['price', 'unit_price', 'unitprice', 'unit price', 'price_per_unit'],
            'Discount': ['discount', 'discount_amount', 'discountamount', 'discount_percent', 'discountpercent'],
            'Tax': ['tax', 'tax_amount', 'taxamount', 'tax_rate', 'taxrate']
        }
        
        detected_mappings = {}
        
        # For each Cin7 field, find matching CSV columns
        for cin7_field, possible_names in field_mappings.items():
            matches = []
            for col in all_columns:
                col_lower = col.lower().strip()
                # Normalize column name for comparison (remove special chars, normalize spaces)
                col_normalized = col_lower.replace('_', ' ').replace('-', ' ').replace('#', '').strip()
                for possible_name in possible_names:
                    possible_normalized = possible_name.lower().replace('_', ' ').replace('-', ' ').replace('#', '').strip()
                    if col_lower == possible_name.lower() or col_normalized == possible_normalized:
                        matches.append(col)
                        break
            
            if matches:
                detected_mappings[cin7_field] = matches
        
        return detected_mappings
    
    def transform_value(self, value: str, field_type: str, date_format: Optional[str] = None) -> Any:
        """
        Transform a CSV value to the appropriate type for Cin7.
        
        Args:
            value: Raw value from CSV
            field_type: Type of field ('date', 'number', 'boolean', 'uuid', 'string')
            date_format: Optional date format override
        
        Returns:
            Transformed value
        """
        if not value or value.strip() == '':
            return None
        
        value = value.strip()
        
        if field_type == 'date':
            return self._parse_date(value, date_format or self.date_format)
        elif field_type == 'number':
            return self._parse_number(value)
        elif field_type == 'boolean':
            return self._parse_boolean(value)
        elif field_type == 'uuid':
            return self._parse_uuid(value)
        else:
            return value
    
    def _parse_date(self, value: str, date_format: str) -> Optional[str]:
        """
        Parse date string and convert to YYYY-MM-DD format.
        
        Supports multiple date formats including:
        - YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY
        - MM/DD/YY (e.g., 12/17/25 -> 2025-12-17)
        - Various other common formats
        
        Args:
            value: Date string to parse
            date_format: Optional format hint (currently unused, formats are auto-detected)
        
        Returns:
            Date string in YYYY-MM-DD format, or None if parsing fails
        """
        if not value:
            return None
        
        value = value.strip()
        
        # Common date formats (ordered by most common first)
        formats = [
            '%Y-%m-%d',      # YYYY-MM-DD (ISO format)
            '%m/%d/%Y',      # MM/DD/YYYY
            '%m/%d/%y',      # MM/DD/YY (e.g., 12/17/25)
            '%d/%m/%Y',      # DD/MM/YYYY
            '%d/%m/%y',      # DD/MM/YY
            '%Y/%m/%d',      # YYYY/MM/DD
            '%d-%m-%Y',      # DD-MM-YYYY
            '%m-%d-%Y',      # MM-DD-YYYY
            '%m-%d-%y',      # MM-DD-YY
            '%d-%m-%y',      # DD-MM-YY
            '%d-%b-%y',      # DD-MMM-YY (e.g., 17-Nov-25)
            '%d-%b-%Y',      # DD-MMM-YYYY (e.g., 17-Nov-2025)
            '%d %b %y',      # DD MMM YY (e.g., 17 Nov 25)
            '%d %b %Y',      # DD MMM YYYY (e.g., 17 Nov 2025)
            '%b %d, %Y',     # MMM DD, YYYY (e.g., Nov 17, 2025)
            '%B %d, %Y',     # MMMM DD, YYYY (e.g., November 17, 2025)
        ]
        
        # Try to parse with common formats
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                # Handle 2-digit years - assume years 00-50 are 2000-2050, 51-99 are 1951-1999
                if fmt.endswith('%y'):  # 2-digit year format
                    # strptime with %y gives years 00-99 as 1900-1999
                    # We want: 00-50 -> 2000-2050, 51-99 -> 1951-1999
                    if dt.year >= 1900 and dt.year <= 1999:
                        two_digit_year = dt.year % 100
                        if two_digit_year <= 50:
                            # 00-50 -> 2000-2050
                            dt = dt.replace(year=2000 + two_digit_year)
                        # else 51-99 stays as 1951-1999 (already correct from strptime)
                
                # Always return in YYYY-MM-DD format
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        # If format string provided, try to use it
        if date_format:
            # Convert format string to strftime format
            fmt_map = {
                'YYYY': '%Y',
                'MM': '%m',
                'DD': '%d',
                'YY': '%y'
            }
            fmt_str = date_format
            for key, val in fmt_map.items():
                fmt_str = fmt_str.replace(key, val)
            
            try:
                dt = datetime.strptime(value, fmt_str)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        return None
    
    def _parse_number(self, value: str) -> Optional[float]:
        """Parse number string"""
        if not value:
            return None
        
        # Remove currency symbols and commas
        cleaned = re.sub(r'[^\d.-]', '', value.replace(',', ''))
        
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    def _parse_boolean(self, value: str) -> bool:
        """Parse boolean string"""
        if not value:
            return False
        
        value_lower = value.lower().strip()
        true_values = ['true', 'yes', 'y', '1', 'on']
        return value_lower in true_values
    
    def _parse_uuid(self, value: str) -> Optional[str]:
        """Parse UUID string"""
        if not value:
            return None
        
        # UUID pattern
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        
        value = value.strip()
        if uuid_pattern.match(value):
            return value
        
        return None



