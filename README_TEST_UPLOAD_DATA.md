# Test Upload Data - test_upload_data.csv

## Description
This CSV file contains fresh test data for verifying the auto-create functionality. All customers and products are designed to be auto-created (they shouldn't exist in your Cin7 sandbox).

## Contents

### Customers (6 unique)
1. **Demo Customer One** - Appears in 2 orders (DEMO-ORDER-001, DEMO-ORDER-005)
2. **Demo Customer Two** - 1 order (DEMO-ORDER-002)
3. **Demo Customer Three** - 1 order (DEMO-ORDER-003)
4. **Demo Customer Four** - 1 order (DEMO-ORDER-004)
5. **Demo Customer Five** - 1 order (DEMO-ORDER-006)
6. **Demo Customer Six** - 1 order (DEMO-ORDER-007) with 2 line items (grouped order)

### Products (8 unique)
1. **DEMO-PROD-100** - Demo Product Alpha (used in DEMO-ORDER-001)
2. **DEMO-PROD-200** - Demo Product Beta (used in DEMO-ORDER-002)
3. **DEMO-PROD-300** - Demo Product Gamma (used in DEMO-ORDER-003)
4. **DEMO-PROD-400** - Demo Product Delta (used in DEMO-ORDER-004)
5. **DEMO-PROD-500** - Demo Product Epsilon (used in DEMO-ORDER-005)
6. **DEMO-PROD-600** - Demo Product Zeta (used in DEMO-ORDER-006)
7. **DEMO-PROD-700** - Demo Product Eta (used in DEMO-ORDER-007)
8. **DEMO-PROD-800** - Demo Product Theta (used in DEMO-ORDER-007)

## Order Summary

| Order # | PO # | Customer | Date | Ship By | Line Items | Total |
|---------|------|----------|------|---------|------------|-------|
| DEMO-ORDER-001 | PO-DEMO-001 | Demo Customer One | 2025-12-30 | 2026-01-05 | 1 | $1,100.00 |
| DEMO-ORDER-002 | PO-DEMO-002 | Demo Customer Two | 2025-12-30 | 2026-01-06 | 1 | $1,487.50 |
| DEMO-ORDER-003 | PO-DEMO-003 | Demo Customer Three | 2025-12-31 | 2026-01-07 | 1 | $1,181.25 |
| DEMO-ORDER-004 | PO-DEMO-004 | Demo Customer Four | 2025-12-31 | 2026-01-08 | 1 | $1,750.00 |
| DEMO-ORDER-005 | PO-DEMO-005 | Demo Customer One | 2026-01-01 | 2026-01-09 | 1 | $1,562.50 |
| DEMO-ORDER-006 | PO-DEMO-006 | Demo Customer Five | 2026-01-01 | 2026-01-10 | 1 | $1,447.50 |
| DEMO-ORDER-007 | PO-DEMO-007 | Demo Customer Six | 2026-01-02 | 2026-01-11 | 2 | $2,490.00 |

**Total Orders**: 7  
**Total Line Items**: 8 (DEMO-ORDER-007 has 2 items, so it's grouped)  
**Grand Total**: $11,019.75

## Expected Behavior

When uploaded with auto-create enabled:

1. **6 customers** will be auto-created:
   - Demo Customer One
   - Demo Customer Two
   - Demo Customer Three
   - Demo Customer Four
   - Demo Customer Five
   - Demo Customer Six

2. **8 products** will be auto-created:
   - DEMO-PROD-100, DEMO-PROD-200, DEMO-PROD-300, DEMO-PROD-400
   - DEMO-PROD-500, DEMO-PROD-600, DEMO-PROD-700, DEMO-PROD-800

3. **7 sales orders** will be created:
   - DEMO-ORDER-001 through DEMO-ORDER-007
   - DEMO-ORDER-007 will be grouped (2 rows = 1 order with 2 line items)

## Column Mapping

The CSV uses these column names that should map to Cin7 fields:

- `Customer Name` → `CustomerName`
- `PO #` → `CustomerReference` (Purchase Order number)
- `Order #` → Optional order identifier (used for grouping, not mapped to Cin7 field)
- `SaleOrderDate` → `SaleOrderDate`
- `ShipBy` → `ShipBy`
- `Item Code` → `SKU`
- `Product Name` → `ProductName`
- `Quantity` → `Quantity`
- `Unit Price` → `UnitPrice`
- `Total` → `LineTotal` (optional, can be calculated)

## Notes

- All dates are in the future (December 2025 - January 2026) to avoid issues with past dates
- Prices are realistic test values ($33.75 - $95.00 per unit)
- DEMO-ORDER-007 demonstrates order grouping (same Order # = same order with multiple line items)
- Demo Customer One appears multiple times to test cache reuse (2 orders)
- All SKUs and customer names use "DEMO" prefix to clearly identify test data



