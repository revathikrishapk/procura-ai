import os

# Base directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Auto-approve threshold ($5,000). Anything above pauses for HITL approval.
AUTO_APPROVE_THRESHOLD = 5000.00

# File paths
MOCK_VENDORS_CSV = os.path.join(BASE_DIR, "data", "mock_vendors.csv")