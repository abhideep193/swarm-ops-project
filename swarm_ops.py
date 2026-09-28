"""
SwarmOps Production-Grade Agent Engine
Provides:
  - DataLoader  – robust CSV/JSON/TXT loading with caching
  - EventBus    – in-memory pub/sub for live dashboard updates
  - Agent base  – standard log(), metrics tracking
  - Four specialist agents: Inventory, Pricing, Customer, Fraud
  - SupervisorAgent – orchestrates routing, conflict resolution, KPI aggregation
"""
import csv
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import config

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("swarm_ops")


# ──────────────────────────────────────────────
# Data Loader (cached)
# ──────────────────────────────────────────────
class DataLoader:
    _inventory: Optional[List[Dict]] = None
    _pricing:   Optional[List[Dict]] = None
    _fraud:     Optional[Dict]       = None
    _policy:    Optional[str]        = None

    @classmethod
    def inventory(cls) -> List[Dict]:
        if cls._inventory is None:
            cls._inventory = cls._load_csv(config.INVENTORY_CSV)
        return cls._inventory

    @classmethod
    def pricing(cls) -> List[Dict]:
        if cls._pricing is None:
            cls._pricing = cls._load_csv(config.PRICING_CSV)
        return cls._pricing

    @classmethod
    def fraud_rules(cls) -> Dict:
        if cls._fraud is None:
            cls._fraud = cls._load_json(config.FRAUD_RULES_JSON)
        return cls._fraud

    @classmethod
    def policy(cls) -> str:
        if cls._policy is None:
            cls._policy = cls._load_text(config.CUSTOMER_POLICY)
        return cls._policy

    @classmethod
    def reload_all(cls):
        cls._inventory = cls._pricing = cls._fraud = cls._policy = None
        cls.inventory(); cls.pricing(); cls.fraud_rules(); cls.policy()

    @staticmethod
    def _load_csv(path: Path) -> List[Dict]:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        except Exception as e:
            logger.error("CSV load failed %s: %s", path, e)
            return []

    @staticmethod
    def _load_json(path: Path) -> Dict:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("JSON load failed %s: %s", path, e)
            return {}

    @staticmethod
    def _load_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Text load failed %s: %s", path, e)
            return ""


# ──────────────────────────────────────────────
# Event Bus  (async, supports WebSocket fans)
# ──────────────────────────────────────────────
class EventBus:
    def __init__(self):
        self._subscribers: List[asyncio.Queue] = []
        self._event_log: List[Dict] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.remove(q)

    def publish(self, event: Dict):
        self._event_log.append(event)
        if len(self._event_log) > config.MAX_LOG_ENTRIES:
            self._event_log.pop(0)
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def recent(self, n: int = 50) -> List[Dict]:
        return list(reversed(self._event_log[-n:]))


# Global event bus
event_bus = EventBus()


# ──────────────────────────────────────────────
# Base Agent
# ──────────────────────────────────────────────
class Agent:
    def __init__(self, name: str, role: str):
        self.name  = name
        self.role  = role
        self._metrics = {"calls": 0, "errors": 0, "last_called": None}

    def log(self, action: str, details: Dict, severity: str = "INFO") -> Dict:
        entry = {
            "agent":     self.name,
            "role":      self.role,
            "action":    action,
            "details":   details,
            "severity":  severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._metrics["calls"] += 1
        self._metrics["last_called"] = entry["timestamp"]
        event_bus.publish(entry)
        return entry

    def error(self, msg: str) -> Dict:
        self._metrics["errors"] += 1
        return self.log("ERROR", {"error": msg}, "ERROR")

    @property
    def health(self) -> Dict:
        return {
            "name":        self.name,
            "role":        self.role,
            "status":      "online",
            "calls":       self._metrics["calls"],
            "errors":      self._metrics["errors"],
            "last_called": self._metrics["last_called"],
        }

    def process(self, input_text: str) -> Dict:
        raise NotImplementedError


# ──────────────────────────────────────────────
# Inventory Agent
# ──────────────────────────────────────────────
class InventoryAgent(Agent):
    def __init__(self):
        super().__init__("InventoryAgent", "Inventory Optimization")

    def process(self, input_text: str) -> Dict:
        text_lower = input_text.lower()
        inventory  = DataLoader.inventory()

        # Extract SKU from input or default to first match
        sku = self._extract_sku(input_text, inventory)
        product = next((i for i in inventory if i["SKU"] == sku), None)
        if not product:
            return self.error(f"Product not found for SKU '{sku}'")

        mumbai    = int(product["stock_mumbai"])
        delhi     = int(product["stock_delhi"])
        bangalore = int(product["stock_bangalore"])
        reorder   = int(product["reorder_point"])
        unit_cost = float(product["unit_cost_inr"])

        # Detect warehouse context
        warehouse = "Delhi"
        stock_level = delhi
        if "mumbai" in text_lower:
            warehouse, stock_level = "Mumbai", mumbai
        elif "bangalore" in text_lower or "bengaluru" in text_lower:
            warehouse, stock_level = "Bangalore", bangalore

        # Override if explicit number mentioned
        import re
        m = re.search(r"(\d+)\s+units?", input_text, re.IGNORECASE)
        if m:
            stock_level = int(m.group(1))

        total_stock   = mumbai + delhi + bangalore
        status        = "Normal"
        action        = "MONITOR"
        cost_impact   = 0.0
        reorder_qty   = 0

        if stock_level < config.INVENTORY_CRITICAL_THRESHOLD:
            status      = "Critical"
            action      = "CRITICAL_REORDER"
            reorder_qty = reorder * 3
            cost_impact = unit_cost * reorder_qty * 0.15  # 15% rush premium savings if reordered now
        elif stock_level < config.INVENTORY_WARNING_THRESHOLD:
            status      = "Warning"
            action      = "WARNING_LOW_STOCK"
            reorder_qty = reorder
            cost_impact = unit_cost * reorder_qty * 0.05

        return self.log(action, {
            "sku":               sku,
            "product_name":      product["product_name"],
            "warehouse":         warehouse,
            "stock_level":       stock_level,
            "total_stock":       total_stock,
            "reorder_point":     reorder,
            "reorder_qty":       reorder_qty,
            "unit_cost_inr":     unit_cost,
            "cost_impact_inr":   round(cost_impact, 2),
            "status":            status,
            "reorder_recommended": stock_level < reorder,
        }, "CRITICAL" if status == "Critical" else "WARNING" if status == "Warning" else "INFO")

    @staticmethod
    def _extract_sku(text: str, inventory: List[Dict]) -> str:
        import re
        m = re.search(r"SKU[-–]?\s*(\w+)", text, re.IGNORECASE)
        if m:
            return "SKU-" + m.group(1).upper()
        # Fuzzy: match product name
        text_lower = text.lower()
        for item in inventory:
            if item["product_name"].lower() in text_lower:
                return item["SKU"]
        return inventory[0]["SKU"] if inventory else "UNKNOWN"


# ──────────────────────────────────────────────
# Pricing Agent
# ──────────────────────────────────────────────
class PricingAgent(Agent):
    def __init__(self):
        super().__init__("PricingAgent", "Dynamic Pricing")

    def process(self, input_text: str) -> Dict:
        pricing = DataLoader.pricing()
        sku     = InventoryAgent._extract_sku(input_text, DataLoader.inventory())
        product = next((p for p in pricing if p["SKU"] == sku), None)
        if not product:
            return self.error(f"Pricing data not found for SKU '{sku}'")

        our_price      = float(product["our_price"])
        flipkart_price = float(product["flipkart_price"])
        amazon_price   = float(product["amazon_price"])
        meesho_price   = float(product["meesho_price"])
        min_margin_pct = float(product["min_margin_percent"])

        # Extract competitor price override from text
        import re
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", input_text)
        if m and ("dropped" in input_text.lower() or "discount" in input_text.lower()):
            drop_pct = float(m.group(1))
            if "flipkart" in input_text.lower():
                flipkart_price = our_price * (1 - drop_pct / 100)
            elif "amazon" in input_text.lower():
                amazon_price = our_price * (1 - drop_pct / 100)

        # Best competitor price
        best_competitor = min(flipkart_price, amazon_price, meesho_price)
        competitor_name = {
            flipkart_price: "Flipkart",
            amazon_price:   "Amazon",
            meesho_price:   "Meesho",
        }[best_competitor]

        diff_pct    = ((our_price - best_competitor) / our_price) * 100
        floor_price = our_price * (1 - (min_margin_pct / 100))

        recommendation = "HOLD"
        new_price      = our_price

        if diff_pct >= config.PRICING_MATCH_THRESHOLD:
            if best_competitor >= floor_price:
                recommendation = "PRICE_MATCH"
                new_price      = round(best_competitor, 2)
            else:
                recommendation = "HOLD_FLOOR_BREACH"
                new_price      = round(floor_price, 2)
        elif diff_pct > 0:
            recommendation = "MONITOR_COMPETITOR"

        margin_after = ((new_price - (our_price * (1 - min_margin_pct / 100 - 0.05))) / new_price) * 100

        return self.log(recommendation, {
            "sku":              sku,
            "product_name":     next((i["product_name"] for i in DataLoader.inventory() if i["SKU"] == sku), sku),
            "our_price":        our_price,
            "best_competitor":  round(best_competitor, 2),
            "competitor_name":  competitor_name,
            "recommended_price":new_price,
            "change_pct":       round(diff_pct, 2),
            "margin_floor_inr": round(floor_price, 2),
            "estimated_margin_pct": round(margin_after, 1),
            "confidence":       "High" if abs(diff_pct) > 5 else "Medium",
        }, "WARNING" if recommendation.startswith("PRICE_MATCH") else "INFO")


# ──────────────────────────────────────────────
# Customer Agent
# ──────────────────────────────────────────────
class CustomerAgent(Agent):
    def __init__(self):
        super().__init__("CustomerAgent", "Customer Service")

    def process(self, input_text: str) -> Dict:
        text_lower = input_text.lower()
        policy     = DataLoader.policy()

        # Sentiment analysis (rule-based)
        sentiment = "Neutral"
        if any(w in text_lower for w in ["angry", "furious", "threatening", "unacceptable", "worst"]):
            sentiment = "Angry"
        elif any(w in text_lower for w in ["happy", "thank", "great", "love"]):
            sentiment = "Positive"
        elif any(w in text_lower for w in ["complaint", "not delivered", "delay", "issue"]):
            sentiment = "Frustrated"

        # Escalation check
        action     = "RESOLVE_STANDARD"
        escalation = None
        severity   = "INFO"

        if any(kw in text_lower for kw in config.ESCALATION_KEYWORDS):
            action     = "ESCALATE_LEGAL"
            escalation = "Legal / Regulatory Threat"
            severity   = "CRITICAL"
        elif "not delivered" in text_lower or "not received" in text_lower:
            action     = "TRACK_AND_COMPENSATE"
            escalation = None
            severity   = "WARNING"
        elif "refund" in text_lower:
            import re
            m = re.search(r"₹?\s*(\d+)", input_text)
            amt = int(m.group(1)) if m else 0
            action   = "REFUND_AUTO" if amt <= config.REFUND_AUTO_APPROVE_LIMIT else "REFUND_MANUAL_REVIEW"
            severity = "INFO"

        # Extract ticket ID
        import re
        tid_m = re.search(r"#?([A-Z]{2,4}\d{4,8})", input_text)
        ticket_id = tid_m.group(1) if tid_m else f"TICKET-{int(time.time()) % 100000}"

        # SLA resolution time
        resolution_eta = {
            "ESCALATE_LEGAL":       "Immediate (Human Agent)",
            "TRACK_AND_COMPENSATE": "2 hours",
            "REFUND_AUTO":          "24 hours",
            "REFUND_MANUAL_REVIEW": "48 hours",
            "RESOLVE_STANDARD":     "4 hours",
        }.get(action, "4 hours")

        compensation = None
        if "deliver" in text_lower and "delay" in text_lower:
            compensation = "₹100 wallet credit (SLA breach)"

        return self.log(action, {
            "ticket_id":      ticket_id,
            "sentiment":      sentiment,
            "action":         action,
            "escalation":     escalation,
            "compensation":   compensation,
            "resolution_eta": resolution_eta,
            "policy_excerpt": policy[:120] + "…" if policy else "N/A",
        }, severity)


# ──────────────────────────────────────────────
# Fraud Agent
# ──────────────────────────────────────────────
class FraudAgent(Agent):
    def __init__(self):
        super().__init__("FraudAgent", "Fraud & Security")

    def process(self, input_text: str) -> Dict:
        rules  = DataLoader.fraud_rules()
        score  = 0
        flags  = []
        text_lower = input_text.lower()

        # Rule: new account + high value order
        r_new = rules.get("rules", {}).get("new_account_high_value", {})
        import re
        amt_m = re.search(r"₹?\s*(\d[\d,]*)", input_text)
        order_amount = 0
        if amt_m:
            order_amount = int(amt_m.group(1).replace(",", ""))
        if ("new account" in text_lower or "new user" in text_lower) and order_amount >= r_new.get("threshold_inr", 5000):
            score += r_new.get("score", 30)
            flags.append(f"New account with high-value order ₹{order_amount}")

        # Rule: velocity / multiple addresses
        r_addr = rules.get("rules", {}).get("address_mismatch", {})
        if re.search(r"\d+\s+different\s+address", text_lower):
            score += r_addr.get("score", 25)
            flags.append("Multiple address changes in short window")

        # Rule: velocity check
        r_vel = rules.get("rules", {}).get("velocity_check", {})
        if "same ip" in text_lower or "same device" in text_lower:
            score += r_vel.get("score", 40)
            flags.append("Velocity: multiple orders from same IP/device")

        # Rule: blacklisted IP
        for ip in rules.get("blacklisted_ips", []):
            if ip in input_text:
                score += 50
                flags.append(f"Blacklisted IP detected: {ip}")

        # Rule: COD high-return-risk
        if "cod" in text_lower or "cash on delivery" in text_lower:
            score += 10
            flags.append("COD payment – elevated return risk")

        # Rule: high-risk pincode
        for pc in rules.get("high_risk_pincodes", []):
            if pc in input_text:
                score += 20
                flags.append(f"High-risk pincode: {pc}")

        score = min(score, 100)

        risk_level = "Low"
        action     = "APPROVE"
        severity   = "INFO"

        if score >= config.FRAUD_CRITICAL_SCORE:
            risk_level = "Critical"
            action     = "BLOCK_TRANSACTION"
            severity   = "CRITICAL"
        elif score >= config.FRAUD_HIGH_SCORE:
            risk_level = "High"
            action     = "MANUAL_REVIEW"
            severity   = "WARNING"
        elif score >= 30:
            risk_level = "Medium"
            action     = "FLAG_FOR_MONITORING"
            severity   = "WARNING"

        return self.log(action, {
            "fraud_score":   score,
            "risk_level":    risk_level,
            "flags":         flags,
            "order_amount":  order_amount,
            "recommendation":action,
        }, severity)


# ──────────────────────────────────────────────
# Supervisor / Orchestrator
# ──────────────────────────────────────────────
class SupervisorAgent:
    def __init__(self):
        self.inventory = InventoryAgent()
        self.pricing   = PricingAgent()
        self.customer  = CustomerAgent()
        self.fraud     = FraudAgent()
        self._kpis = {
            "inventory_cost_saved":   0.0,
            "revenue_protected":      0.0,
            "fraud_blocked_inr":      0.0,
            "fraud_blocked_count":    0,
            "queries_resolved":       0,
            "price_matches":          0,
            "critical_alerts":        0,
            "total_events_processed": 0,
        }

    @property
    def agents(self) -> List[Agent]:
        return [self.inventory, self.pricing, self.customer, self.fraud]

    def route(self, text: str) -> List[Agent]:
        """Classify text and return list of agents to invoke."""
        t     = text.lower()
        agents = []

        # Hard rules (order matters for efficiency)
        if any(k in t for k in ["fraud", "new account", "new user", "same ip", "cod", "address"]):
            agents.append(self.fraud)
        if any(k in t for k in ["stock", "warehouse", "sku", "inventory", "units", "reorder"]):
            agents.append(self.inventory)
        if any(k in t for k in ["price", "flipkart", "amazon", "meesho", "discount", "sale"]):
            agents.append(self.pricing)
        if any(k in t for k in ["customer", "deliver", "complaint", "refund", "ticket", "order #",
                                 "legal", "forum", "return"]):
            agents.append(self.customer)

        # Multi-agent trigger (flash-sale scenario)
        if "flash sale" in t or "mega sale" in t:
            agents = list(dict.fromkeys([self.inventory, self.pricing, self.fraud] + agents))

        # ≥1 agent guaranteed
        if not agents:
            agents = [self.inventory]  # default fallback

        return agents

    def process(self, input_text: str) -> Dict:
        start_ts = datetime.now(timezone.utc)
        agents_to_call = self.route(input_text)
        responses: List[Dict] = []

        for agent in agents_to_call:
            try:
                resp = agent.process(input_text)
                responses.append(resp)
            except Exception as exc:
                logger.exception("Agent %s failed: %s", agent.name, exc)
                responses.append(agent.error(str(exc)))

        outcome = self._resolve_conflicts(responses)
        self._update_kpis(responses, outcome)
        self._kpis["total_events_processed"] += 1

        end_ts = datetime.now(timezone.utc)
        processing_ms = round((end_ts - start_ts).total_seconds() * 1000, 1)

        return {
            "input":           input_text,
            "routed_to":       [a.name for a in agents_to_call],
            "agent_responses": responses,
            "final_outcome":   outcome,
            "kpi_snapshot":    self._kpis.copy(),
            "processing_ms":   processing_ms,
            "timestamp":       end_ts.isoformat(),
        }

    def _resolve_conflicts(self, responses: List[Dict]) -> Dict:
        by_agent = {r["agent"]: r for r in responses}
        notes    = []
        status   = "EXECUTED"

        # P0: Fraud Critical → block everything
        if "FraudAgent" in by_agent:
            fd = by_agent["FraudAgent"]
            if fd.get("details", {}).get("risk_level") == "Critical":
                return {
                    "status":         "BLOCKED_BY_FRAUD",
                    "notes":          ["Fraud score critical. All operations halted."],
                    "primary_action": fd,
                }

        # P1: Customer Legal Escalation
        if "CustomerAgent" in by_agent:
            ca = by_agent["CustomerAgent"]
            if ca["action"] == "ESCALATE_LEGAL":
                notes.append("Customer legal escalation in progress – Pricing changes paused.")
                by_agent.pop("PricingAgent", None)

        # P2: Inventory Critical overrides Pricing discounts
        if "InventoryAgent" in by_agent and "PricingAgent" in by_agent:
            inv = by_agent["InventoryAgent"]
            pri = by_agent["PricingAgent"]
            if inv.get("details", {}).get("status") == "Critical" and pri.get("action", "").startswith("PRICE_MATCH"):
                notes.append(
                    "Pricing discount DENIED – insufficient inventory to fulfil demand at lower price."
                )
                status = "PARTIAL_OVERRIDE"

        return {
            "status":  status,
            "notes":   notes,
            "actions": list(by_agent.values()),
        }

    def _update_kpis(self, responses: List[Dict], outcome: Dict):
        for r in responses:
            d = r.get("details", {})
            if r.get("agent") == "InventoryAgent":
                self._kpis["inventory_cost_saved"] += d.get("cost_impact_inr", 0)
                if d.get("status") == "Critical":
                    self._kpis["critical_alerts"] += 1
            elif r.get("agent") == "FraudAgent":
                if d.get("risk_level") in ("Critical", "High"):
                    self._kpis["fraud_blocked_inr"]   += d.get("order_amount", 0)
                    self._kpis["fraud_blocked_count"] += 1
                    self._kpis["critical_alerts"]     += 1
            elif r.get("agent") == "CustomerAgent":
                self._kpis["queries_resolved"] += 1
            elif r.get("agent") == "PricingAgent":
                if r.get("action") == "PRICE_MATCH":
                    self._kpis["price_matches"] += 1

    @property
    def kpis(self) -> Dict:
        return self._kpis.copy()

    @property
    def health(self) -> List[Dict]:
        return [a.health for a in self.agents]


# ──────────────────────────────────────────────
# Simulation Runner
# ──────────────────────────────────────────────
TEST_INPUTS = [
    "SKU-4521 stock in Delhi warehouse dropped to 15 units",
    "Flipkart dropped price on iPhone 15 case by 12%",
    "Customer order #IND8821 not delivered in 7 days, threatening consumer forum complaint",
    "New account, ₹8500 order, COD, 3 different addresses in last 10 mins from same IP",
    "Flash sale starts in 1 hour, stock critically low on top 3 SKUs, 2 fraud alerts pending",
    "SKU-1122 Samsung Galaxy S24 reorder required, Mumbai warehouse at 10 units",
    "Amazon dropped Sony WH-1000XM5 by 8%",
    "Customer ticket #IND9922 refund ₹450 requested for damaged headphones",
]

def run_simulation(supervisor: SupervisorAgent = None) -> List[Dict]:
    if supervisor is None:
        supervisor = SupervisorAgent()
    results = []
    logger.info("Starting SwarmOps simulation with %d inputs", len(TEST_INPUTS))
    for i, inp in enumerate(TEST_INPUTS):
        logger.info("Processing input %d/%d: %s", i + 1, len(TEST_INPUTS), inp[:50])
        result = supervisor.process(inp)
        results.append(result)
        time.sleep(config.SIMULATION_DELAY_MS / 1000)
    with open(config.LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    logger.info("Simulation complete. %d events logged to %s", len(results), config.LOG_FILE)
    return results


if __name__ == "__main__":
    run_simulation()