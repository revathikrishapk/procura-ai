from app.services.database_service import (
    find_product,
    find_suppliers_for_product
)


company_id = "COMP-001"

product = find_product(
    company_id,
    "NVIDIA H100"
)

if product:

    print("PRODUCT FOUND")
    print("Product:", product.name)

    suppliers = find_suppliers_for_product(
        company_id,
        product.id
    )

    print("Suppliers found:", len(suppliers))

    for supplier, supplier_product in suppliers:
        print(
            supplier.name,
            "₹",
            supplier_product.last_price
        )

else:

    print("PRODUCT NOT FOUND")