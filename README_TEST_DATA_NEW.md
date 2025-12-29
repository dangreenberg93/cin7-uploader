# Test Upload Data - test_data_new.csv

## Description
This CSV file contains fresh test data with different column names and structure. All customers and products are designed to be auto-created (they shouldn't exist in your Cin7 sandbox).

## Contents

### Customers (6 unique)
1. **Acme Corporation** - Appears in 2 orders (PURCH-001, PURCH-004)
2. **Tech Solutions Inc** - 1 order (PURCH-002)
3. **Global Enterprises** - 1 order (PURCH-003)
4. **MegaCorp Industries** - 1 order (PURCH-005)
5. **Alpha Beta Gamma** - 1 order (PURCH-006)
6. **Beta Gamma Delta** - 1 order (PURCH-007) with 2 line items (grouped order)

### Products (8 unique)
1. **ACME-WIDGET-01** - Widget Model A (used in PURCH-001)
2. **TECH-GADGET-X1** - Gadget X1 Standard (used in PURCH-002)
3. **GLOB-ITEM-500** - Enterprise Item 500 (used in PURCH-003)
4. **ACME-WIDGET-02** - Widget Model B (used in PURCH-004)
5. **MEGA-PROD-900** - Mega Product 900 (used in PURCH-005)
6. **ABG-UNIT-100** - Unit 100 Base (used in PURCH-006)
7. **BGD-SPEC-200** - Special Item 200 (used in PURCH-007)
8. **BGD-SPEC-300** - Special Item 300 (used in PURCH-007)

## Order Summary

| PO # | Customer | Date | Ship Date | Line Items | Total |
|------|----------|------|-----------|------------|-------|
| PURCH-001 | Acme Corporation | 2026-01-15 | 2026-01-20 | 1 | $1,299.00 |
| PURCH-002 | Tech Solutions Inc | 2026-01-15 | 2026-01-22 | 1 | $1,837.50 |
| PURCH-003 | Global Enterprises | 2026-01-16 | 2026-01-25 | 1 | $4,499.50 |
| PURCH-004 | Acme Corporation | 2026-01-16 | 2026-01-21 | 1 | $3,150.00 |
| PURCH-005 | MegaCorp Industries | 2026-01-17 | 2026-01-26 | 1 | $4,166.25 |
| PURCH-006 | Alpha Beta Gamma | 2026-01-17 | 2026-01-27 | 1 | $1,699.20 |
| PURCH-007 | Beta Gamma Delta | 2026-01-18 | 2026-01-28 | 2 | $3,295.00 |

**Total Orders**: 7  
**Total Line Items**: 8 (PURCH-007 has 2 items, so it's grouped)  
**Grand Total**: $19,946.45

## Column Mapping

The CSV uses these column names that should map to Cin7 fields:

- `Customer` → `CustomerName`
- `Purchase Order` → `CustomerReference` (PO number)
- `Date` → `SaleOrderDate`
- `Ship Date` → `ShipBy`
- `SKU` → `SKU`
- `Description` → `ProductName`
- `Qty` → `Quantity`
- `Price` → `UnitPrice`
- `Extended` → `LineTotal` (optional, can be calculated)

## Notes

- **Different column names**: Uses shorter, more business-friendly names (Customer, Purchase Order, Date, Ship Date, SKU, Description, Qty, Price, Extended)
- All dates are in the future (January 2026) to avoid issues with past dates
- Prices range from $12.99 to $89.99 per unit
- Quantities range from 40 to 200 units
- PURCH-007 demonstrates order grouping (same PO # = same order with multiple line items)
- Acme Corporation appears twice to test cache reuse (2 orders)
- All SKUs use different prefixes (ACME-, TECH-, GLOB-, MEGA-, ABG-, BGD-) for easy identification
- Product names are more descriptive (e.g., "Widget Model A" instead of "Alpha Product One")



