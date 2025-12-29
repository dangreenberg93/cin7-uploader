# Test Upload Data - test_upload_new.csv

## Description
This CSV file contains test data for verifying the auto-create functionality. All customers and products in this file are designed to be auto-created (they shouldn't exist in your Cin7 sandbox).

## Contents

### Customers (5 unique)
1. **Test Customer Alpha** - Appears in 2 orders (ORDER-001, ORDER-005)
2. **Test Customer Beta** - Appears in 2 orders (ORDER-002, ORDER-006)
3. **Test Customer Gamma** - 1 order (ORDER-003)
4. **Test Customer Delta** - 1 order (ORDER-004)
5. **Test Customer Epsilon** - 1 order (ORDER-007) with 2 line items (grouped order)

### Products (7 unique)
1. **TEST-PROD-ALPHA-001** - Alpha Product One (used in ORDER-001)
2. **TEST-PROD-ALPHA-002** - Alpha Product Two (used in ORDER-005)
3. **TEST-PROD-BETA-001** - Beta Product One (used in ORDER-002)
4. **TEST-PROD-BETA-002** - Beta Product Two (used in ORDER-006)
5. **TEST-PROD-GAMMA-001** - Gamma Product One (used in ORDER-003)
6. **TEST-PROD-DELTA-001** - Delta Product One (used in ORDER-004)
7. **TEST-PROD-EPSILON-001** - Epsilon Product One (used in ORDER-007)
8. **TEST-PROD-EPSILON-002** - Epsilon Product Two (used in ORDER-007)

## Order Summary

| Order # | PO # | Customer | Date | Ship By | Line Items | Total |
|---------|------|----------|------|---------|------------|-------|
| ORDER-001 | PO-2025-001 | Test Customer Alpha | 2025-12-25 | 2025-12-28 | 1 | $1,137.50 |
| ORDER-002 | PO-2025-002 | Test Customer Beta | 2025-12-25 | 2025-12-29 | 1 | $1,600.00 |
| ORDER-003 | PO-2025-003 | Test Customer Gamma | 2025-12-26 | 2025-12-30 | 1 | $862.50 |
| ORDER-004 | PO-2025-004 | Test Customer Delta | 2025-12-26 | 2025-12-31 | 1 | $2,200.00 |
| ORDER-005 | PO-2025-005 | Test Customer Alpha | 2025-12-27 | 2025-12-29 | 1 | $1,012.50 |
| ORDER-006 | PO-2025-006 | Test Customer Beta | 2025-12-27 | 2025-12-30 | 1 | $845.00 |
| ORDER-007 | PO-2025-007 | Test Customer Epsilon | 2025-12-28 | 2025-12-31 | 2 | $2,611.50 |

**Total Orders**: 7  
**Total Line Items**: 8 (ORDER-007 has 2 items, so it's grouped)  
**Grand Total**: $10,269.00

## Expected Behavior

When uploaded with auto-create enabled:

1. **5 customers** will be auto-created:
   - Test Customer Alpha
   - Test Customer Beta
   - Test Customer Gamma
   - Test Customer Delta
   - Test Customer Epsilon

2. **7 products** will be auto-created:
   - TEST-PROD-ALPHA-001, TEST-PROD-ALPHA-002
   - TEST-PROD-BETA-001, TEST-PROD-BETA-002
   - TEST-PROD-GAMMA-001
   - TEST-PROD-DELTA-001
   - TEST-PROD-EPSILON-001, TEST-PROD-EPSILON-002

3. **7 sales orders** will be created:
   - ORDER-001 through ORDER-007
   - ORDER-007 will be grouped (2 rows = 1 order)

## Column Mapping

The CSV uses these column names that should map to Cin7 fields:

- `Customer Name` → `CustomerName`
- `PO #` → `CustomerReference` (Purchase Order number)
- `Order #` → Optional order identifier (not mapped to Cin7 field, used for grouping)
- `SaleOrderDate` → `SaleOrderDate`
- `ShipBy` → `ShipBy`
- `Item Code` → `SKU`
- `Product Name` → `ProductName`
- `Quantity` → `Quantity`
- `Unit Price` → `UnitPrice`
- `Total` → `LineTotal` (optional, can be calculated)

## Notes

- All dates are in the future (December 2025) to avoid issues with past dates
- Prices are realistic test values
- ORDER-007 demonstrates order grouping (same Order # = same order with multiple line items)
- Some customers appear multiple times to test cache reuse (Alpha and Beta have 2 orders each)

