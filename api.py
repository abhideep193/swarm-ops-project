"""
SwarmOps FastAPI REST + WebSocket Server
Endpoints:
  POST /api/process         – process a natural-language / JSON event
  GET  /api/kpis            – live KPI snapshot
  GET  /api/agents          – agent health status
  GET  /api/logs            – recent activity log
  POST /api/simulation/run  – run full test simulation
  WS   /ws/live             – real-time event stream
"""
import asyncio
import json
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from swarm_ops import SupervisorAgent, event_bus, run_simulation, TEST_INPUTS, DataLoader

# ── Singleton supervisor ──────────────────────────────
supervisor: Optional[SupervisorAgent] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global supervisor
    DataLoader.reload_all()
    supervisor = SupervisorAgent()
    yield

# ── App ───────────────────────────────────────────────
app = FastAPI(
    title="SwarmOps Intelligence Platform",
    version="2.0.0",
    description="Production multi-agent swarm for e-commerce operations",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve dashboard
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(str(config.BASE_DIR / "dashboard.html"))


# ── Models ────────────────────────────────────────────
class ProcessRequest(BaseModel):
    input: str
    context: Optional[Dict[str, Any]] = None


# ── REST Endpoints ────────────────────────────────────
@app.post("/api/process")
async def process_event(req: ProcessRequest):
    """Route an event through the swarm and return the result."""
    if not req.input.strip():
        return {"error": "Input cannot be empty"}, 400
    result = supervisor.process(req.input)
    return result


@app.get("/api/kpis")
async def get_kpis():
    """Return current KPI snapshot."""
    return supervisor.kpis


@app.get("/api/agents")
async def get_agents():
    """Return health status of all agents."""
    return {"agents": supervisor.health}


@app.get("/api/logs")
async def get_logs(n: int = 50):
    """Return the last N events from the event bus."""
    return {"logs": event_bus.recent(n)}


@app.post("/api/simulation/run")
async def run_sim():
    """Run the full built-in test simulation in a background thread."""
    def _run():
        run_simulation(supervisor)
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"status": "simulation_started", "inputs": len(TEST_INPUTS)}


@app.get("/api/simulation/inputs")
async def get_sim_inputs():
    return {"inputs": TEST_INPUTS}


# ── WebSocket ─────────────────────────────────────────
@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    queue = event_bus.subscribe()
    # Send last 20 events on connect
    for ev in event_bus.recent(20):
        await websocket.send_text(json.dumps(ev))
    try:
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=30)
            await websocket.send_text(json.dumps(event))
    except asyncio.TimeoutError:
        await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        event_bus.unsubscribe(queue)


# ── Entry point ───────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host=config.API_HOST, port=config.API_PORT, reload=True)
