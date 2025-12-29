# Test File for Auto-Create Functionality

## File: `test_auto_create.csv`

This test file is designed to test the auto-create customers and products functionality.

### Test Data Overview

- **5 CSV rows** (4 data rows + 1 header)
- **4 unique customers** (all will be auto-created):
  - Auto Test Customer One (AUTO001)
  - Auto Test Customer Two (AUTO002)
  - Auto Test Customer Three (AUTO003)
  - Auto Test Customer Four (AUTO004)

- **4 unique products/SKUs** (all will be auto-created):
  - AUTO-SKU-100 (Test Product One 750ML)
  - AUTO-SKU-101 (Test Product Two 500ML)
  - AUTO-SKU-102 (Test Product Three 750ML)
  - AUTO-SKU-103 (Test Product Four 1L)

- **4 orders** (grouped by Order # / PO #):
  - AUTO-TEST-001 (AUTO-PO-001): 2 line items (tests grouping)
  - AUTO-TEST-002 (AUTO-PO-002): 1 line item
  - AUTO-TEST-003 (AUTO-PO-003): 1 line item
  - AUTO-TEST-004 (AUTO-PO-004): 1 line item

### Expected Behavior

When you upload this file with auto-create enabled:

1. **Validation Step:**
   - Should show warnings that 4 customers are not found
   - Should show warnings that 4 products are not found
   - Should show 4 orders grouped correctly

2. **Create Orders Step:**
   - Should auto-create 4 customers (Auto Test Customer One, Two, Three, Four)
   - Should auto-create 4 products (AUTO-SKU-100, 101, 102, 103)
   - Should create 4 sales in Cin7
   - Should create 4 sales orders in Cin7
   - All orders should be successful

3. **Verification:**
   - Check API logs for 4 POST /customer calls (Status 200)
   - Check API logs for 4 POST /product calls (Status 200)
   - Check API logs for 4 POST /sale calls (Status 200)
   - Check API logs for 4 POST /saleorder calls (Status 200)

### How to Test

1. Open the web UI
2. Select the **PBD Sandbox** profile (ensure auto-create is enabled)
3. Upload `test_auto_create.csv`
4. Verify column mappings:
   - `SKU` → "Item Code" (may need to set manually)
   - `CustomerName` → "Customer Name"
   - `CustomerReference` → "PO #"
   - `SaleOrderDate` → "Date"
   - `Price` → "Price"
   - `Quantity` → "Quantity Ordered"
5. Click **"Validate"** - should show warnings but allow through
6. Click **"Create Orders"**
7. Verify all 4 orders are successful
8. Check Cin7 to confirm customers and products were created
9. Check API logs to confirm all API calls succeeded

### Notes

- All customer names start with "Auto Test Customer" to easily identify test data
- All SKUs start with "AUTO-SKU-" to easily identify test products
- All PO numbers start with "AUTO-PO-" to easily identify test orders
- This is a sandbox account, so test data is acceptable
- You can delete these test customers/products/orders after testing



