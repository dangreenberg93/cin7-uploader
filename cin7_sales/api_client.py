"""
Cin7/Dear Systems API Client for Sales Orders
"""
import time
import requests
from urllib.parse import urlencode
from typing import Dict, Any, Tuple, Optional, List, Callable
from datetime import datetime


class Cin7SalesAPI:
    """Client for Dear Systems/Cin7 Sales API"""
    
    def __init__(self, account_id: str, application_key: str, 
                 base_url: str = "https://inventory.dearsystems.com/ExternalApi/v2/",
                 logger_callback: Optional[Callable] = None):
        """
        Initialize the API client.
        
        Args:
            account_id: Your account ID (UUID string)
            application_key: Your application key
            base_url: Base URL for the API
            logger_callback: Optional callback function to log API calls.
                           Should accept: (endpoint, method, request_url, request_headers,
                           request_body, response_status, response_body, error_message, duration_ms)
        """
        self.account_id = account_id
        self.application_key = application_key
        self.base_url = base_url.rstrip('/')
        self.logger_callback = logger_callback
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api-auth-accountid": account_id,
            "api-auth-applicationkey": application_key
        })
        self.last_request_time = 0
        self.min_request_interval = 0.34  # ~3 requests per second (slightly conservative)
    
    def _rate_limit(self):
        """Enforce rate limiting (3 req/sec, 60 req/min)"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _build_query_string(self, params: Dict[str, Any]) -> str:
        """Build query string from parameters"""
        return urlencode(params)
    
    def _handle_response(self, response: requests.Response, endpoint: str, method: str,
                         request_url: str, request_headers: dict, request_body: Any,
                         start_time: float) -> Tuple[bool, str, Optional[Any]]:
        """Handle API response and extract error messages"""
        duration_ms = int((time.time() - start_time) * 1000)
        response_body = None
        error_message = None
        
        try:
            response_body = response.json() if response.content else None
        except:
            response_body = response.text[:1000] if response.text else None
        
        if response.status_code == 200:
            success = True
            message = "Success"
            result = response_body
        elif response.status_code == 429:
            success = False
            message = "Rate limit exceeded. Please wait and try again."
            error_message = message
            result = None
        elif response.status_code == 401:
            success = False
            message = "Authentication failed. Check your credentials."
            error_message = message
            result = None
        elif response.status_code == 400:
            try:
                error_msg = self._extract_error_message(response_body) if response_body else response.text[:200]
                success = False
                message = f"Bad request: {error_msg}"
                error_message = message
                result = response_body
            except:
                success = False
                message = f"Bad request: {response.text[:200] if response.text else 'Unknown error'}"
                error_message = message
                result = None
        elif response.status_code == 422:
            try:
                error_msg = self._extract_error_message(response_body) if response_body else response.text[:200]
                success = False
                message = f"Validation error: {error_msg}"
                error_message = message
                result = response_body
            except:
                success = False
                message = f"Validation error: {response.text[:200] if response.text else 'Unknown error'}"
                error_message = message
                result = None
        elif response.status_code == 500:
            success = False
            message = "Server error. Please try again later."
            error_message = message
            result = None
        else:
            try:
                error_msg = self._extract_error_message(response_body) if response_body else response.text[:500] if response.text else f"HTTP {response.status_code}"
                success = False
                message = f"HTTP {response.status_code}: {error_msg}"
                error_message = message
                result = response_body
            except:
                error_text = response.text[:500] if response.text else f"HTTP {response.status_code}"
                success = False
                message = f"HTTP {response.status_code}: {error_text}"
                error_message = message
                result = None
        
        # Log the API call if callback is provided
        if self.logger_callback:
            # Sanitize headers (remove sensitive keys)
            safe_headers = {k: v for k, v in request_headers.items() 
                          if k.lower() not in ['api-auth-applicationkey', 'authorization']}
            self.logger_callback(
                endpoint=endpoint,
                method=method,
                request_url=request_url,
                request_headers=safe_headers,
                request_body=request_body,
                response_status=response.status_code,
                response_body=response_body,
                error_message=error_message,
                duration_ms=duration_ms
            )
        
        return (success, message, result)
    
    def _extract_error_message(self, error_json: Any) -> str:
        """Extract error message from API error response"""
        if isinstance(error_json, list) and len(error_json) > 0:
            error_obj = error_json[0]
            error_code = error_obj.get("ErrorCode", "")
            exception = error_obj.get("Exception", "")
            message = error_obj.get("Message", "")
            if exception:
                return f"{error_code}: {exception}"
            elif message:
                return message
            else:
                return str(error_obj)
        elif isinstance(error_json, dict):
            if "Message" in error_json:
                return error_json["Message"]
            elif "Exception" in error_json:
                return error_json["Exception"]
            else:
                return str(error_json)
        else:
            return str(error_json)
    
    def create_sale(self, sale_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Any]]:
        """
        Create a Sale.
        
        Args:
            sale_data: Dictionary containing the sale data
        
        Returns:
            (success, message, response_data)
        """
        self._rate_limit()
        url = f"{self.base_url}/sale"
        endpoint = "/sale"
        method = "POST"
        start_time = time.time()
        
        try:
            response = self.session.post(url, json=sale_data, timeout=30)
            return self._handle_response(response, endpoint, method, url, 
                                       dict(self.session.headers), sale_data, start_time)
        except requests.exceptions.Timeout:
            duration_ms = int((time.time() - start_time) * 1000)
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=sale_data,
                    response_status=None,
                    response_body=None,
                    error_message="Request timeout",
                    duration_ms=duration_ms
                )
            return (False, "Request timeout", None)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=sale_data,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return (False, error_msg, None)
    
    def create_sale_order(self, sale_order_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Any]]:
        """
        Create a Sale Order.
        
        Args:
            sale_order_data: Dictionary containing the sale order data (with SaleID, Total, Tax, Lines)
        
        Returns:
            (success, message, response_data)
        """
        self._rate_limit()
        url = f"{self.base_url}/saleorder"
        endpoint = "/saleorder"
        method = "POST"
        start_time = time.time()
        
        try:
            response = self.session.post(url, json=sale_order_data, timeout=30)
            return self._handle_response(response, endpoint, method, url,
                                       dict(self.session.headers), sale_order_data, start_time)
        except requests.exceptions.Timeout:
            duration_ms = int((time.time() - start_time) * 1000)
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=sale_order_data,
                    response_status=None,
                    response_body=None,
                    error_message="Request timeout",
                    duration_ms=duration_ms
                )
            return (False, "Request timeout", None)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=sale_order_data,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return (False, error_msg, None)
    
    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a customer record by ID.
        
        Args:
            customer_id: The unique identifier (ID) of the customer
        
        Returns:
            Customer data or None if not found
        """
        self._rate_limit()
        url = f"{self.base_url}/customer"
        endpoint = "/customer"
        method = "GET"
        params = {"id": customer_id}
        start_time = time.time()
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}",
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                if data.get("CustomerList") and len(data["CustomerList"]) > 0:
                    return data["CustomerList"][0]
            return None
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}",
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return None
    
    def search_customer(self, email: Optional[str] = None, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for customers by email or name.
        
        Args:
            email: Customer email to search for
            name: Customer name to search for
        
        Returns:
            List of matching customers
        """
        self._rate_limit()
        url = f"{self.base_url}/customer"
        endpoint = "/customer"
        method = "GET"
        params = {}
        
        if email:
            params["email"] = email
        if name:
            params["name"] = name
        
        start_time = time.time()
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}" if params else url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                return data.get("CustomerList", [])
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}" if params else url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return []
    
    def get_product(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Get a product by SKU.
        
        Args:
            sku: Product SKU
        
        Returns:
            Product data or None if not found
        """
        self._rate_limit()
        url = f"{self.base_url}/product"
        endpoint = "/product"
        method = "GET"
        params = {"SKU": sku}
        start_time = time.time()
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}",
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                if data.get("Products") and len(data["Products"]) > 0:
                    return data["Products"][0]
            return None
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}",
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return None
    
    def search_product(self, sku: Optional[str] = None, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for products by SKU or name.
        
        Args:
            sku: Product SKU to search for
            name: Product name to search for
        
        Returns:
            List of matching products
        """
        self._rate_limit()
        url = f"{self.base_url}/product"
        endpoint = "/product"
        method = "GET"
        params = {}
        
        if sku:
            params["SKU"] = sku
        if name:
            params["Name"] = name
        
        start_time = time.time()
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}" if params else url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                return data.get("Products", [])
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}" if params else url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return []
    
    def get_company(self) -> Optional[Dict[str, Any]]:
        """
        Get company information (for testing connection).
        Uses /me endpoint to verify credentials.
        
        Returns:
            Company data or None
        """
        import sys
        print(f"DEBUG get_company: logger_callback is {'SET' if self.logger_callback else 'NOT SET'}", file=sys.stderr, flush=True)
        if self.logger_callback:
            print(f"DEBUG get_company: logger_callback type: {type(self.logger_callback)}", file=sys.stderr, flush=True)
        else:
            print(f"DEBUG get_company: logger_callback is NOT SET - API call will NOT be logged!", file=sys.stderr, flush=True)
            print(f"DEBUG get_company: self.logger_callback value: {self.logger_callback}", file=sys.stderr, flush=True)
        self._rate_limit()
        url = f"{self.base_url}/me"
        endpoint = "/me"
        method = "GET"
        start_time = time.time()
        
        try:
            response = self.session.get(url, timeout=10)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            # IMPORTANT: Call logger_callback BEFORE returning, regardless of status code
            # This ensures the API call is always logged
            import sys
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                print(f"DEBUG: About to call logger_callback for {method} {endpoint} (get_company)", file=sys.stderr, flush=True)
                print(f"DEBUG: logger_callback type: {type(self.logger_callback)}", file=sys.stderr, flush=True)
                print(f"DEBUG: logger_callback is callable: {callable(self.logger_callback)}", file=sys.stderr, flush=True)
                try:
                    self.logger_callback(
                        endpoint=endpoint,
                        method=method,
                        request_url=url,
                        request_headers=safe_headers,
                        request_body=None,
                        response_status=response.status_code,
                        response_body=response_body,
                        error_message=error_message,
                        duration_ms=duration_ms
                    )
                    print(f"DEBUG: logger_callback completed for {method} {endpoint}", file=sys.stderr, flush=True)
                except Exception as callback_error:
                    print(f"DEBUG: ERROR in logger_callback: {str(callback_error)}", file=sys.stderr, flush=True)
                    import traceback
                    print(traceback.format_exc(), file=sys.stderr, flush=True)
            else:
                print(f"DEBUG: No logger_callback set for {method} {endpoint} - API call will NOT be logged!", file=sys.stderr, flush=True)
                print(f"DEBUG: self.logger_callback value: {self.logger_callback}", file=sys.stderr, flush=True)
            
            if response.status_code == 200:
                # Check if response is actually valid JSON (not HTML error page)
                if response_body and isinstance(response_body, dict):
                    return response_body
                elif response_body and isinstance(response_body, str) and '<!DOCTYPE html>' in response_body:
                    # Got HTML error page instead of JSON
                    print(f"WARNING: API returned HTML instead of JSON: {response_body[:200]}")
                    return None
                return response_body if response_body else None
            return None
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return None
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        Get all accounts from Cin7.
        
        Returns:
            List of account dictionaries
        """
        # Store debug info on instance for access by caller (similar to locations)
        self._last_account_response = None
        self._last_account_raw_data = None
        
        self._rate_limit()
        base = self.base_url.rstrip('/')
        url = f"{base}/ref/account"
        endpoint = "/ref/account"
        method = "GET"
        params = {
            'Page': 1,
            'Limit': 100
        }
        start_time = time.time()
        
        import sys
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"DEBUG get_accounts: Making API call to {url}", file=sys.stderr)
        print(f"DEBUG get_accounts: Method: {method}", file=sys.stderr)
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                
                # Store for debugging (similar to locations)
                self._last_account_response = {
                    'status': response.status_code,
                    'data_type': str(type(data)),
                    'data': data,
                    'is_list': isinstance(data, list),
                    'is_dict': isinstance(data, dict),
                    'keys': list(data.keys()) if isinstance(data, dict) else None,
                    'raw_text': response.text[:1000] if hasattr(response, 'text') and response.text else None
                }
                self._last_account_raw_data = data
                
                # Check for HTML error page
                if isinstance(data, str) and '<!DOCTYPE html>' in data:
                    import sys
                    print(f"DEBUG get_accounts: Received HTML error page", file=sys.stderr)
                    print(f"{'='*60}\n", file=sys.stderr)
                    return []
                
                # Debug: print response structure (similar to locations)
                import sys
                raw_response_text = response.text[:500] if hasattr(response, 'text') else None
                print(f"DEBUG get_accounts: Response status 200, data type: {type(data)}", file=sys.stderr)
                print(f"DEBUG get_accounts: Response data: {data}", file=sys.stderr)
                print(f"DEBUG get_accounts: Raw response text (first 500 chars): {raw_response_text}", file=sys.stderr)
                print(f"DEBUG get_accounts: Response data keys (if dict): {list(data.keys()) if isinstance(data, dict) else 'N/A'}", file=sys.stderr)
                
                # Extract accounts from response (similar to LocationList pattern)
                accounts = []
                if isinstance(data, list):
                    print(f"DEBUG get_accounts: Data is a list with {len(data)} items", file=sys.stderr)
                    print(f"{'='*60}\n", file=sys.stderr)
                    return data
                elif isinstance(data, dict):
                    print(f"DEBUG get_accounts: Data is a dict with keys: {list(data.keys())}", file=sys.stderr)
                    # Use AccountsList (the actual key from API response)
                    accounts = data.get('AccountsList', [])
                    print(f"DEBUG get_accounts: Extracted {len(accounts) if accounts else 0} accounts from AccountsList", file=sys.stderr)
                    if isinstance(accounts, list):
                        print(f"DEBUG get_accounts: Returning {len(accounts)} accounts", file=sys.stderr)
                        print(f"{'='*60}\n", file=sys.stderr)
                        return accounts
                    elif isinstance(accounts, dict):
                        print(f"DEBUG get_accounts: Single account object, wrapping in list", file=sys.stderr)
                        print(f"{'='*60}\n", file=sys.stderr)
                        return [accounts]
                else:
                    print(f"DEBUG get_accounts: Unexpected data type: {type(data)}", file=sys.stderr)
            else:
                import sys
                print(f"DEBUG get_accounts: Non-200 status: {response.status_code}", file=sys.stderr)
                print(f"DEBUG get_accounts: Response text: {response.text[:200] if response.text else 'None'}", file=sys.stderr)
            import sys
            print(f"DEBUG get_accounts: Returning empty list", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
            return []
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return []
    
    def get_tax_rules(self) -> List[Dict[str, Any]]:
        """
        Get all tax rules from Cin7.
        
        Returns:
            List of tax rule dictionaries
        """
        # Store debug info on instance for access by caller (similar to locations)
        self._last_tax_response = None
        self._last_tax_raw_data = None
        
        self._rate_limit()
        base = self.base_url.rstrip('/')
        url = f"{base}/ref/tax"
        endpoint = "/ref/tax"
        method = "GET"
        params = {
            'Page': 1,
            'Limit': 100
        }
        start_time = time.time()
        
        import sys
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"DEBUG get_tax_rules: Making API call to {url}", file=sys.stderr)
        print(f"DEBUG get_tax_rules: Method: {method}", file=sys.stderr)
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                
                # Store for debugging (similar to locations)
                self._last_tax_response = {
                    'status': response.status_code,
                    'data_type': str(type(data)),
                    'data': data,
                    'is_list': isinstance(data, list),
                    'is_dict': isinstance(data, dict),
                    'keys': list(data.keys()) if isinstance(data, dict) else None,
                    'raw_text': response.text[:1000] if hasattr(response, 'text') and response.text else None
                }
                self._last_tax_raw_data = data
                
                # Check for HTML error page
                if isinstance(data, str) and '<!DOCTYPE html>' in data:
                    import sys
                    print(f"DEBUG get_tax_rules: Received HTML error page", file=sys.stderr)
                    print(f"{'='*60}\n", file=sys.stderr)
                    return []
                
                # Debug: print response structure (similar to locations)
                import sys
                raw_response_text = response.text[:500] if hasattr(response, 'text') else None
                print(f"DEBUG get_tax_rules: Response status 200, data type: {type(data)}", file=sys.stderr)
                print(f"DEBUG get_tax_rules: Response data: {data}", file=sys.stderr)
                print(f"DEBUG get_tax_rules: Raw response text (first 500 chars): {raw_response_text}", file=sys.stderr)
                print(f"DEBUG get_tax_rules: Response data keys (if dict): {list(data.keys()) if isinstance(data, dict) else 'N/A'}", file=sys.stderr)
                
                # Extract tax rules from response (similar to LocationList pattern)
                tax_rules = []
                if isinstance(data, list):
                    print(f"DEBUG get_tax_rules: Data is a list with {len(data)} items", file=sys.stderr)
                    print(f"{'='*60}\n", file=sys.stderr)
                    return data
                elif isinstance(data, dict):
                    print(f"DEBUG get_tax_rules: Data is a dict with keys: {list(data.keys())}", file=sys.stderr)
                    # Use TaxRuleList (the actual key from API response)
                    tax_rules = data.get('TaxRuleList', [])
                    print(f"DEBUG get_tax_rules: Extracted {len(tax_rules) if tax_rules else 0} tax rules from TaxRuleList", file=sys.stderr)
                    if isinstance(tax_rules, list):
                        print(f"DEBUG get_tax_rules: Returning {len(tax_rules)} tax rules", file=sys.stderr)
                        print(f"{'='*60}\n", file=sys.stderr)
                        return tax_rules
                    elif isinstance(tax_rules, dict):
                        print(f"DEBUG get_tax_rules: Single tax rule object, wrapping in list", file=sys.stderr)
                        print(f"{'='*60}\n", file=sys.stderr)
                        return [tax_rules]
                else:
                    import sys
                    print(f"DEBUG get_tax_rules: Unexpected data type: {type(data)}", file=sys.stderr)
            else:
                import sys
                print(f"DEBUG get_tax_rules: Non-200 status: {response.status_code}", file=sys.stderr)
                print(f"DEBUG get_tax_rules: Response text: {response.text[:200] if response.text else 'None'}", file=sys.stderr)
            import sys
            print(f"DEBUG get_tax_rules: Returning empty list", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
            return []
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return []
    
    def get_attribute_sets(self) -> List[Dict[str, Any]]:
        """
        Get all attribute sets from Cin7.
        
        Returns:
            List of attribute set dictionaries
        """
        self._last_attribute_set_response = None  # Reset debug info
        self._rate_limit()
        base = self.base_url.rstrip('/')
        url = f"{base}/ref/attributeset"
        endpoint = "/ref/attributeset"
        method = "GET"
        params = {
            'Page': 1,
            'Limit': 100
        }
        start_time = time.time()
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)
            
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            # Store debug info
            self._last_attribute_set_response = {
                'status': response.status_code,
                'data_type': str(type(response_body)),
                'data': response_body,
                'is_list': isinstance(response_body, list),
                'is_dict': isinstance(response_body, dict),
                'keys': list(response_body.keys()) if isinstance(response_body, dict) else None,
                'raw_text': response.text[:1000] if hasattr(response, 'text') and response.text else None
            }
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                # Check for HTML error page
                if isinstance(data, str) and '<!DOCTYPE html>' in data:
                    import sys
                    print(f"DEBUG get_attribute_sets: Received HTML error page", file=sys.stderr)
                    return []
                
                # Debug: print response structure (similar to locations)
                import sys
                print(f"DEBUG get_attribute_sets: Response status: {response.status_code}", file=sys.stderr)
                print(f"DEBUG get_attribute_sets: Data type: {type(data)}", file=sys.stderr)
                
                # Extract attribute sets from response (similar to LocationList pattern)
                attribute_sets = []
                if isinstance(data, list):
                    print(f"DEBUG get_attribute_sets: Data is a list with {len(data)} items", file=sys.stderr)
                    attribute_sets = data
                elif isinstance(data, dict):
                    print(f"DEBUG get_attribute_sets: Data is a dict with keys: {list(data.keys())}", file=sys.stderr)
                    # Use AttributeSetList (the actual key from API response)
                    attribute_sets = data.get('AttributeSetList', [])
                    print(f"DEBUG get_attribute_sets: Extracted {len(attribute_sets) if attribute_sets else 0} attribute sets from AttributeSetList", file=sys.stderr)
                
                if isinstance(attribute_sets, list):
                    print(f"DEBUG get_attribute_sets: Returning {len(attribute_sets)} attribute sets", file=sys.stderr)
                    return attribute_sets
                return []
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return []
    
    def get_locations(self) -> List[Dict[str, Any]]:
        """
        Get all locations from Cin7.
        
        Returns:
            List of location dictionaries
        """
        # Store debug info on instance for access by caller
        self._last_location_response = None
        self._last_location_raw_data = None
        
        self._rate_limit()
        # Ensure base_url ends with /, then add ref/location
        base = self.base_url.rstrip('/')
        url = f"{base}/ref/location"
        endpoint = "/ref/location"
        method = "GET"
        # Add query parameters (only include non-empty values)
        params = {
            'Page': 1,
            'Deprecated': 'false'
        }
        start_time = time.time()
        
        import sys
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"DEBUG get_locations: Making API call to {url}", file=sys.stderr)
        print(f"DEBUG get_locations: Method: {method}", file=sys.stderr)
        print(f"DEBUG get_locations: Headers (sanitized): api-auth-accountid={self.account_id[:8]}..., api-auth-applicationkey=***", file=sys.stderr)
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            print(f"DEBUG get_locations: Response status: {response.status_code}", file=sys.stderr)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                # Store for debugging
                self._last_location_response = {
                    'status': response.status_code,
                    'data_type': str(type(data)),
                    'data': data,
                    'is_list': isinstance(data, list),
                    'is_dict': isinstance(data, dict),
                    'keys': list(data.keys()) if isinstance(data, dict) else None,
                    'raw_text': response.text[:1000] if hasattr(response, 'text') and response.text else None
                }
                self._last_location_raw_data = data
                
                # Also capture raw response text for debugging
                raw_response_text = response.text[:500] if hasattr(response, 'text') else None
                print(f"DEBUG get_locations: Response status 200, data type: {type(data)}", file=sys.stderr)
                print(f"DEBUG get_locations: Response data: {data}", file=sys.stderr)
                print(f"DEBUG get_locations: Raw response text (first 500 chars): {raw_response_text}", file=sys.stderr)
                print(f"DEBUG get_locations: Response data keys (if dict): {list(data.keys()) if isinstance(data, dict) else 'N/A'}", file=sys.stderr)
                
                # API returns locations in a dict with LocationList key (similar to CustomerList)
                if isinstance(data, list):
                    print(f"DEBUG get_locations: Data is a list with {len(data)} items", file=sys.stderr)
                    print(f"{'='*60}\n", file=sys.stderr)
                    return data
                elif isinstance(data, dict):
                    print(f"DEBUG get_locations: Data is a dict with keys: {list(data.keys())}", file=sys.stderr)
                    # Cin7 API returns locations in LocationList key
                    locations = data.get('LocationList', [])
                    print(f"DEBUG get_locations: Extracted {len(locations) if locations else 0} locations from LocationList", file=sys.stderr)
                    if isinstance(locations, list):
                        print(f"DEBUG get_locations: Returning {len(locations)} locations", file=sys.stderr)
                        print(f"{'='*60}\n", file=sys.stderr)
                        return locations
                    # If it's a single location object, wrap it in a list
                    elif isinstance(locations, dict):
                        print(f"DEBUG get_locations: Single location object, wrapping in list", file=sys.stderr)
                        print(f"{'='*60}\n", file=sys.stderr)
                        return [locations]
                else:
                    print(f"DEBUG get_locations: Unexpected data type: {type(data)}", file=sys.stderr)
            else:
                print(f"DEBUG get_locations: Non-200 status: {response.status_code}", file=sys.stderr)
                print(f"DEBUG get_locations: Response text: {response.text[:200] if response.text else 'None'}", file=sys.stderr)
            print(f"DEBUG get_locations: Returning empty list", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            print(f"Error fetching locations: {str(e)}")
            return []
    
    def validate_customer(self, customer_id: str) -> Tuple[bool, str]:
        """
        Validate that a customer exists.
        
        Args:
            customer_id: Customer ID to validate
        
        Returns:
            (is_valid, message)
        """
        customer = self.get_customer(customer_id)
        if customer:
            return (True, "Customer exists")
        else:
            return (False, "Customer not found")
    
    def validate_product(self, sku: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate that a product exists.
        
        Args:
            sku: Product SKU to validate
        
        Returns:
            (is_valid, message, product_id)
        """
        product = self.get_product(sku)
        if product:
            product_id = product.get("ID")
            return (True, "Product exists", product_id)
        else:
            return (False, "Product not found", None)
    
    def get_all_customers(self, limit: Optional[int] = None, page: int = 1) -> List[Dict[str, Any]]:
        """
        Get all customers from Cin7.
        
        Args:
            limit: Maximum number of customers to return (None for all)
            page: Page number for pagination (default: 1)
        
        Returns:
            List of all customers
        """
        if self.logger_callback:
            print(f"DEBUG get_all_customers: logger_callback is SET")
        else:
            print(f"DEBUG get_all_customers: logger_callback is NOT SET - API calls will not be logged!")
        self._rate_limit()
        url = f"{self.base_url}/customer"
        endpoint = "/customer"
        method = "GET"
        params = {"page": page}
        
        if limit:
            params["limit"] = limit
        
        try:
            start_time = time.time()
            response = self.session.get(url, params=params, timeout=60)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}",
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                customers = data.get("CustomerList", [])
                total_count = data.get("Total")  # Total number of items available
                
                # Check if there are more pages
                if not limit and len(customers) > 0:
                    all_customers = customers[:]
                    
                    # Calculate how many pages we need based on Total
                    if total_count is not None and total_count > len(customers):
                        # Calculate items per page from first page
                        items_per_page = len(customers)
                        # Calculate total pages needed (round up)
                        import math
                        total_pages = math.ceil(total_count / items_per_page) if items_per_page > 0 else 1
                        max_pages = min(total_pages, 100)  # Safety limit
                    else:
                        # If no Total field or we already have all items, don't request more
                        max_pages = page
                    
                    current_page = page + 1
                    
                    while current_page <= max_pages:
                        self._rate_limit()
                        params["page"] = current_page
                        start_time = time.time()
                        response = self.session.get(url, params=params, timeout=60)
                        duration_ms = int((time.time() - start_time) * 1000)
                        
                        # Log pagination calls
                        page_response_body = None
                        page_error_message = None
                        try:
                            page_response_body = response.json() if response.content else None
                        except:
                            page_response_body = response.text[:1000] if response.text else None
                        
                        if response.status_code != 200:
                            page_error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
                        
                        if self.logger_callback:
                            safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                                          if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                            self.logger_callback(
                                endpoint=endpoint,
                                method=method,
                                request_url=f"{url}?{self._build_query_string(params)}",
                                request_headers=safe_headers,
                                request_body=None,
                                response_status=response.status_code,
                                response_body=page_response_body,
                                error_message=page_error_message,
                                duration_ms=duration_ms
                            )
                        
                        if response.status_code == 200:
                            page_data = page_response_body if page_response_body else {}
                            page_customers = page_data.get("CustomerList", [])
                            if not page_customers:
                                break
                            all_customers.extend(page_customers)
                            
                            # Check if we've collected all items
                            if total_count is not None and len(all_customers) >= total_count:
                                break
                            
                            current_page += 1
                        else:
                            break
                    
                    return all_customers
                
                return customers
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}" if 'params' in locals() else url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            print(f"Error fetching all customers: {str(e)}")
            return []
    
    def get_all_products(self, limit: Optional[int] = None, page: int = 1) -> List[Dict[str, Any]]:
        """
        Get all products from Cin7.
        
        Args:
            limit: Maximum number of products to return (None for all)
            page: Page number for pagination (default: 1)
        
        Returns:
            List of all products
        """
        self._rate_limit()
        url = f"{self.base_url}/product"
        endpoint = "/product"
        method = "GET"
        params = {"page": page}
        
        if limit:
            params["limit"] = limit
        
        try:
            start_time = time.time()
            response = self.session.get(url, params=params, timeout=60)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log the API call
            response_body = None
            error_message = None
            try:
                response_body = response.json() if response.content else None
            except:
                response_body = response.text[:1000] if response.text else None
            
            if response.status_code != 200:
                error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
            
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}",
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=response.status_code,
                    response_body=response_body,
                    error_message=error_message,
                    duration_ms=duration_ms
                )
            
            if response.status_code == 200:
                data = response_body if response_body else {}
                products = data.get("Products", [])
                total_count = data.get("Total")  # Total number of items available
                
                # Check if there are more pages
                if not limit and len(products) > 0:
                    all_products = products[:]
                    
                    # Calculate how many pages we need based on Total
                    if total_count is not None and total_count > len(products):
                        # Calculate items per page from first page
                        items_per_page = len(products)
                        # Calculate total pages needed (round up)
                        import math
                        total_pages = math.ceil(total_count / items_per_page) if items_per_page > 0 else 1
                        max_pages = min(total_pages, 100)  # Safety limit
                    else:
                        # If no Total field or we already have all items, don't request more
                        max_pages = page
                    
                    current_page = page + 1
                    
                    while current_page <= max_pages:
                        self._rate_limit()
                        params["page"] = current_page
                        start_time = time.time()
                        response = self.session.get(url, params=params, timeout=60)
                        duration_ms = int((time.time() - start_time) * 1000)
                        
                        # Log pagination calls
                        page_response_body = None
                        page_error_message = None
                        try:
                            page_response_body = response.json() if response.content else None
                        except:
                            page_response_body = response.text[:1000] if response.text else None
                        
                        if response.status_code != 200:
                            page_error_message = f"HTTP {response.status_code}: {response.text[:200] if response.text else 'Unknown error'}"
                        
                        if self.logger_callback:
                            safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                                          if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                            self.logger_callback(
                                endpoint=endpoint,
                                method=method,
                                request_url=f"{url}?{self._build_query_string(params)}",
                                request_headers=safe_headers,
                                request_body=None,
                                response_status=response.status_code,
                                response_body=page_response_body,
                                error_message=page_error_message,
                                duration_ms=duration_ms
                            )
                        
                        if response.status_code == 200:
                            page_data = page_response_body if page_response_body else {}
                            page_products = page_data.get("Products", [])
                            if not page_products:
                                break
                            all_products.extend(page_products)
                            
                            # Check if we've collected all items
                            if total_count is not None and len(all_products) >= total_count:
                                break
                            
                            current_page += 1
                        else:
                            break
                    
                    return all_products
                
                return products
            return []
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
            error_msg = str(e)[:200]
            if self.logger_callback:
                safe_headers = {k: v for k, v in dict(self.session.headers).items() 
                              if k.lower() not in ['api-auth-applicationkey', 'authorization']}
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=f"{url}?{self._build_query_string(params)}" if 'params' in locals() else url,
                    request_headers=safe_headers,
                    request_body=None,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            print(f"Error fetching all products: {str(e)}")
            return []
    
    def create_customer(self, customer_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Create a new customer in Cin7.
        
        Args:
            customer_data: Dictionary containing customer data (Name is required)
        
        Returns:
            (success, message, customer_data)
        """
        self._rate_limit()
        url = f"{self.base_url}/customer"
        endpoint = "/customer"
        method = "POST"
        start_time = time.time()
        
        try:
            response = self.session.post(url, json=customer_data, timeout=30)
            return self._handle_response(response, endpoint, method, url,
                                       dict(self.session.headers), customer_data, start_time)
        except requests.exceptions.Timeout:
            duration_ms = int((time.time() - start_time) * 1000)
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=customer_data,
                    response_status=None,
                    response_body=None,
                    error_message="Request timeout",
                    duration_ms=duration_ms
                )
            return (False, "Request timeout", None)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=customer_data,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return (False, error_msg, None)
    
    def create_customer_address(self, customer_id: str, address_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Create a new address for a customer in Cin7.
        
        Args:
            customer_id: Customer ID (UUID)
            address_data: Dictionary containing address data (Type, Line1, City, etc.)
        
        Returns:
            (success, message, address_data)
        """
        self._rate_limit()
        url = f"{self.base_url}/customeraddress"
        endpoint = "/customeraddress"
        method = "POST"
        start_time = time.time()
        
        # Add CustomerID to address data
        address_payload = {**address_data, 'CustomerID': customer_id}
        
        try:
            response = self.session.post(url, json=address_payload, timeout=30)
            return self._handle_response(response, endpoint, method, url,
                                       dict(self.session.headers), address_payload, start_time)
        except requests.exceptions.Timeout:
            duration_ms = int((time.time() - start_time) * 1000)
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=address_payload,
                    response_status=None,
                    response_body=None,
                    error_message="Request timeout",
                    duration_ms=duration_ms
                )
            return (False, "Request timeout", None)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)[:200]
            if self.logger_callback:
                self.logger_callback(
                    endpoint=endpoint,
                    method=method,
                    request_url=url,
                    request_headers=dict(self.session.headers),
                    request_body=address_payload,
                    response_status=None,
                    response_body=None,
                    error_message=error_msg,
                    duration_ms=duration_ms
                )
            return (False, error_msg, None)

