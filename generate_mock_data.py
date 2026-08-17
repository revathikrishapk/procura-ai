import pandas as pd
import os

def generate_data():
    data = [
        {"vendor_id": "VEND-001", "name": "TechCorp Logistics", "category": "laptops", "rating": 4.8, "unit_price": 750.00},
        {"vendor_id": "VEND-002", "name": "Global Systems Ltd", "category": "laptops", "rating": 4.2, "unit_price": 680.00},
        {"vendor_id": "VEND-003", "name": "Apex Hardware Direct", "category": "laptops", "rating": 4.9, "unit_price": 820.00},
        {"vendor_id": "VEND-004", "name": "NextGen Supplies", "category": "laptops", "rating": 3.9, "unit_price": 610.00},
        {"vendor_id": "VEND-005", "name": "OfficeDepot Hub", "category": "monitors", "rating": 4.5, "unit_price": 220.00},
        {"vendor_id": "VEND-006", "name": "DisplayTech Wholesale", "category": "monitors", "rating": 4.6, "unit_price": 195.00},
        {"vendor_id": "VEND-007", "name": "ErgoFurn Direct", "category": "chairs", "rating": 4.7, "unit_price": 310.00},
    ]
    
    # Pad out to ~30 synthetic records dynamically
    for i in range(8, 31):
        data.append({
            "vendor_id": f"VEND-{i:03d}",
            "name": f"Enterprise Partner {i}",
            "category": "laptops" if i % 2 == 0 else "monitors",
            "rating": round(3.5 + (i % 15) * 0.1, 1),
            "unit_price": float(500 + (i * 12))
        })
        
    df = pd.DataFrame(data)
    out_dir = os.path.dirname(os.path.abspath(__file__))
    df.to_csv(os.path.join(out_dir, "mock_vendors.csv"), index=False)
    print("✓ Successfully generated mock_vendors.csv")

if __name__ == "__main__":
    generate_data()