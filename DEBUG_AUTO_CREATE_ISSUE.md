# Debug Auto-Create Issue

## User's Error Messages

The user is seeing these errors after clicking "Create Orders":

1. **"Validation Error"** - "No valid products found - all products were unmatched"
2. **"Data Missing"** - "Customer 'X' not found in Cin7 | SKU 'Y' not found in Cin7"

## Analysis

### Error Source
These errors are likely coming from the **CREATE step**, not the validation step, because:
- The user clicked "Create Orders" 
- The errors show up as "Validation Error" and "Data Missing" statuses
- These are error types that come from the create/processing step

### Root Cause Hypothesis

The auto-create logic runs **before** `build_sale()`, but there may be an issue with:

1. **Cache not being properly updated** - Products/customers are auto-created, but `builder.preloaded_products` and `builder._product_cache` aren't updated correctly
2. **Builder instance mismatch** - Different builder instances between auto-create and build_sale
3. **Timing issue** - Database commits aren't completed before build_sale runs

### Code Flow

```
1. Auto-create customers/products (lines 982-1253)
   - Creates customers/products via API
   - Updates builder.preloaded_customers/products
   - Updates builder._customer_cache/_product_cache
   - Commits database cache
   - Adds 0.1s delay

2. build_sale() called (line 1256)
   - Calls _lookup_customer_by_name()
   - Should find customer from cache

3. build_sale_order_from_rows() called (line 1300)
   - Calls _build_lines()
   - Calls _lookup_product_by_sku() for each product
   - Should find products from cache
```

### Potential Issues

1. **Cache key mismatch** - Customer cache keys use `f"{customer_name}|{additional_attribute1}"` format. If additional_attribute1 is None vs not provided, keys might not match.

2. **Product cache lookup** - `_lookup_product_by_sku` checks:
   - `self._product_cache[sku]` first
   - Then `self.preloaded_products` (with case variations)
   - If preloaded_products exists (even if empty), it won't fall back to API

3. **Cache update timing** - Even with 0.1s delay and db.session.commit(), there might be a race condition

## Recommended Debugging Steps

1. **Add logging** to verify:
   - Are customers/products being auto-created? (Check API logs)
   - Are cache updates happening? (Log cache contents after auto-create)
   - Are lookups finding cached data? (Log cache contents during build_sale)

2. **Check server logs** for:
   - Auto-create API calls (POST /customer, POST /product)
   - Any exceptions during auto-create
   - Cache update operations

3. **Verify builder instance** - Ensure the same builder instance is used for auto-create and build_sale

4. **Test with a single order** - Simplify to isolate the issue

## Current Status

The end-to-end test passes, suggesting the logic is correct. The issue may be:
- Environmental (database timing, API responses)
- Execution-related (exceptions being caught silently)
- Cache key matching issues in production



