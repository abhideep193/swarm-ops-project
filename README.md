# 🌐 SwarmOps Intelligence Platform v2.0

A **production-grade multi-agent AI swarm** for e-commerce operations, featuring real-time orchestration, conflict resolution, a FastAPI backend, and a live WebSocket dashboard.

## 🚀 Features

| Feature | Description |
|---------|-------------|
| 🧠 **4 Specialist Agents** | Inventory, Pricing, Customer Service, Fraud Detection |
| ⚡ **Real-time WebSocket** | Live event stream to the dashboard |
| 📊 **FastAPI Backend** | REST API + Swagger docs at `/docs` |
| 🎨 **Glassmorphism UI** | Dark mode dashboard with Chart.js trend charts |
| 🔐 **Smart Conflict Resolution** | Priority-based: Fraud → Legal → Inventory → Pricing |
| 🧪 **40 Pytest Tests** | Full coverage of all agents and orchestrator |

## 📁 Project Structure

```
swarm_ops_project/
├── api.py                  # FastAPI server (REST + WebSocket)
├── swarm_ops.py            # Multi-agent engine + EventBus
├── config.py               # Centralized configuration
├── dashboard.html          # Production dashboard UI
├── start.bat               # One-click Windows launcher
├── requirements.txt        # Python dependencies
├── data/
│   ├── mock_inventory.csv  # 8 product SKUs
│   ├── mock_pricing.csv    # Competitor pricing (Flipkart/Amazon/Meesho)
│   ├── fraud_rules.json    # Rule engine for fraud detection
│   └── customer_policy.txt # Service policy document
└── tests/
    └── test_agents.py      # 40 automated tests
```

## ⚙️ Installation

```bash
pip install -r requirements.txt
```

## ▶️ Running

**Windows (one click):**
```
start.bat
```

**Manual:**
```bash
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Then open **http://localhost:8000**

## 🔗 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/process` | Process a natural-language event |
| `GET` | `/api/kpis` | Live KPI snapshot |
| `GET` | `/api/agents` | Agent health status |
| `GET` | `/api/logs` | Recent activity log |
| `POST` | `/api/simulation/run` | Run 8 built-in test scenarios |
| `WS` | `/ws/live` | Real-time event stream |

Interactive docs: **http://localhost:8000/docs**

## 🧪 Testing

```bash
pytest tests/ -v
# 40 passed
```

## 🤖 Agent Architecture

```
SupervisorAgent (Orchestrator)
├── InventoryAgent   → Stock alerts, reorder recommendations, cost impact
├── PricingAgent     → Multi-competitor comparison, margin-floor enforcement
├── CustomerAgent    → Sentiment, SLA, escalation, refund classification
└── FraudAgent       → Rule engine: velocity, IP blacklist, pincode risk, COD
```

## 🧑‍💻 Tech Stack

- **Backend:** Python, FastAPI, uvicorn, WebSockets
- **Frontend:** Vanilla JS, Chart.js, CSS Glassmorphism
- **Testing:** pytest
- **Data:** CSV, JSON, TXT rule files
