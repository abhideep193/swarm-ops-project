"""
SwarmOps Production Configuration
Centralises all paths, thresholds, and tuning parameters.
"""
import os
from pathlib import Path

# ---------- Paths ----------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

INVENTORY_CSV   = DATA_DIR / "mock_inventory.csv"
PRICING_CSV     = DATA_DIR / "mock_pricing.csv"
FRAUD_RULES_JSON= DATA_DIR / "fraud_rules.json"
CUSTOMER_POLICY = DATA_DIR / "customer_policy.txt"
LOG_FILE        = BASE_DIR / "swarm_simulation_log.json"

# ---------- API ----------
API_HOST = os.getenv("SWARM_HOST", "0.0.0.0")
API_PORT = int(os.getenv("SWARM_PORT", "8000"))
CORS_ORIGINS = ["*"]

# ---------- Agent Thresholds ----------
INVENTORY_CRITICAL_THRESHOLD = 20    # units
INVENTORY_WARNING_THRESHOLD  = 50    # units
FRAUD_CRITICAL_SCORE         = 70    # 0-100
FRAUD_HIGH_SCORE             = 50    # 0-100
PRICING_MATCH_THRESHOLD      = 8.0   # % competitor cheaper → match
PRICING_MIN_MARGIN           = 15.0  # % absolute floor

# ---------- SLA & Timeouts ----------
ESCALATION_KEYWORDS = ["consumer forum", "legal", "police", "court", "ncdrc"]
DELIVERY_DELAY_SLA_DAYS = 2           # days before compensation kicks in
REFUND_AUTO_APPROVE_LIMIT = 500       # INR

# ---------- Simulation ----------
SIMULATION_DELAY_MS = 300             # ms between steps
MAX_LOG_ENTRIES = 500                 # cap in-memory event log
