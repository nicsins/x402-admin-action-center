"""
x402 Services Action Center — Vercel serverless entry (FastAPI + Mangum)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

try:
    from mangum import Mangum
except ImportError:
    Mangum = None

MARKETPLACE_URL = os.getenv("MARKETPLACE_URL", "https://x402-micro-pay.com").rstrip("/")
GATEWAY_URL = os.getenv("X402_GATEWAY_URL", MARKETPLACE_URL).rstrip("/")

app = FastAPI(title="x402 Services Action Center", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"


async def _fetch_live() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "reachable": False,
        "health": {},
        "catalog": {},
        "partners": {},
        "manifest": {},
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            h = await client.get(f"{MARKETPLACE_URL}/health")
            c = await client.get(f"{MARKETPLACE_URL}/api/catalog")
            p = await client.get(f"{MARKETPLACE_URL}/api/partners")
            m = await client.get(f"{MARKETPLACE_URL}/.well-known/x402")
            out["reachable"] = h.is_success
            if h.is_success:
                out["health"] = h.json()
            if c.is_success:
                out["catalog"] = c.json()
            if p.is_success:
                out["partners"] = p.json()
            if m.is_success:
                out["manifest"] = m.json()
    except Exception as e:
        out["error"] = str(e)
    return out


def _actions(live: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    health = live.get("health") or {}
    catalog = live.get("catalog") or {}
    partners = live.get("partners") or {}

    if not live.get("reachable"):
        actions.append({
            "priority": "critical",
            "category": "uptime",
            "title": "Marketplace unreachable",
            "detail": live.get("error") or "health check failed",
            "action": "Check Vercel deployment for x402-micro-pay.com",
        })
        return actions

    if health.get("free_beta") is True:
        actions.append({
            "priority": "high",
            "category": "pricing",
            "title": "Free beta still enabled",
            "detail": "FREE_BETA is true on live",
            "action": "Set FREE_BETA=false in production env and redeploy",
        })
    if not health.get("stripe_enabled"):
        actions.append({
            "priority": "high",
            "category": "payments",
            "title": "Stripe not enabled",
            "detail": "Card payments inactive",
            "action": "Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY",
        })
    if not health.get("x402_enabled"):
        actions.append({
            "priority": "high",
            "category": "payments",
            "title": "x402 not enabled",
            "detail": "Agent wallet rail inactive",
            "action": "Set EVM_WALLET / PAY_TO_ADDRESS",
        })

    for skill in catalog.get("skills") or []:
        price = float(skill.get("price_usd") or 0)
        if 0 < price < 0.01:
            actions.append({
                "priority": "medium",
                "category": "pricing",
                "title": f"Low list price: {skill.get('id')}",
                "detail": f"${price} — Stripe floors near $0.50",
                "action": "Reprice via pricing.protocol.price_on_create",
            })

    if partners.get("listing_status") and partners.get("listing_status") != "paid":
        actions.append({
            "priority": "medium",
            "category": "partners",
            "title": "Partners not paid mode",
            "detail": f"listing_status={partners.get('listing_status')}",
            "action": "Deploy partner catalog with paid + 3x cost multiplier",
        })

    actions.append({
        "priority": "info",
        "category": "discovery",
        "title": "Agent discovery surfaces",
        "detail": "catalog, manifest, docs, applet",
        "action": "Share /.well-known/x402 and /api/catalog with agent directories",
    })
    actions.append({
        "priority": "info",
        "category": "discovery",
        "title": "Getting noticed checklist",
        "detail": "x402 lists, humanless contract, CLI maintainer",
        "action": "Index on x402 discovery; run CLI maintainer weekly",
    })

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    actions.sort(key=lambda a: order.get(a["priority"], 9))
    return actions


@app.get("/api/action-center")
async def action_center():
    live = await _fetch_live()
    health = live.get("health") or {}
    catalog = live.get("catalog") or {}
    partners_payload = live.get("partners") or {}
    manifest = live.get("manifest") or {}

    native = [{
        "id": s.get("id"),
        "name": s.get("name"),
        "price_usd": s.get("price_usd"),
        "endpoint": s.get("endpoint"),
        "category": s.get("category"),
        "docs_url": s.get("docs_url"),
        "status": "live" if live.get("reachable") else "unknown",
    } for s in (catalog.get("skills") or [])]

    partner_services = []
    for p in partners_payload.get("partners") or catalog.get("hosted_partners") or []:
        for svc in p.get("services") or []:
            partner_services.append({
                "partner_id": p.get("id") or p.get("partner_id"),
                "provider": p.get("provider"),
                "service_id": svc.get("id"),
                "name": svc.get("name"),
                "price_usd": svc.get("price_usd"),
                "partner_price_usd": svc.get("partner_price_usd"),
                "listing_status": p.get("listing_status"),
                "status": "paid" if p.get("listing_status") == "paid" else p.get("listing_status"),
            })

    actions = _actions(live)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "marketplace_url": MARKETPLACE_URL,
        "reachable": live.get("reachable"),
        "flags": {
            "x402_enabled": health.get("x402_enabled"),
            "stripe_enabled": health.get("stripe_enabled"),
            "free_beta": health.get("free_beta"),
            "network": health.get("network") or (manifest.get("services") or [{}])[0].get("network"),
            "pay_to": health.get("pay_to") or manifest.get("pay_to"),
            "billing_mode": manifest.get("billing_mode"),
        },
        "native_services": native,
        "partner_services": partner_services,
        "partner_listing_status": partners_payload.get("listing_status"),
        "actions": actions,
        "action_counts": {
            "critical": sum(1 for a in actions if a["priority"] == "critical"),
            "high": sum(1 for a in actions if a["priority"] == "high"),
            "medium": sum(1 for a in actions if a["priority"] == "medium"),
            "low": sum(1 for a in actions if a["priority"] == "low"),
            "info": sum(1 for a in actions if a["priority"] == "info"),
        },
        "top_services_db": [],
        "error": live.get("error"),
    }


@app.get("/api/overview")
async def overview():
    live = await _fetch_live()
    health = live.get("health") or {}
    gw_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{GATEWAY_URL}/health")
            gw_ok = r.is_success
    except Exception:
        gw_ok = live.get("reachable", False)

    return {
        "db_connected": False,
        "total_calls": 0,
        "success_calls": 0,
        "error_calls": 0,
        "total_revenue_usd": 0.0,
        "active_agents": 0,
        "pending_payments": 0,
        "gateway": {"reachable": gw_ok, "body": health},
        "hermes_ledger_entries": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Serverless Action Center — full call metrics need DATABASE_URL on a long-running host",
    }


@app.get("/api/calls")
async def calls():
    return []


@app.get("/api/payments")
async def payments():
    return []


@app.get("/api/services")
async def services():
    live = await _fetch_live()
    return [
        {"service": s.get("id"), "call_count": 0, "success_count": 0, "avg_latency_ms": 0}
        for s in (live.get("catalog") or {}).get("skills") or []
    ]


@app.get("/api/opportunities")
async def opportunities():
    return []


@app.get("/api/hermes/status")
async def hermes_status():
    return {
        "ledger_path": None,
        "ledger_exists": False,
        "recent_entries": 0,
        "recent_paid_calls": 0,
        "recent_success": 0,
        "gateway_url": GATEWAY_URL,
        "last_entry": None,
        "note": "Hermes ledger is local-file based; use Docker admin for full Hermes panel",
    }


@app.post("/api/hermes/test-call")
async def hermes_test():
    return JSONResponse(
        status_code=501,
        content={"ok": False, "error": "Hermes test-call requires Docker admin with bridge + ledger"},
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "x402-admin-action-center",
        "marketplace_url": MARKETPLACE_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    index = PUBLIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>x402 Action Center</h1><p>public/index.html missing</p>")


handler = Mangum(app) if Mangum else None
