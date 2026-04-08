"""Page routes — serves the HTML pages for the dashboard."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from demo.config import DemoConfig
from demo.data.patients import list_patients

router = APIRouter()
templates = Jinja2Templates(directory="demo/templates")


def _render(
    name: str, request: Request, context: dict[str, Any]
) -> HTMLResponse:
    context["request"] = request
    return templates.TemplateResponse(request, name, context)


@router.get("/", response_class=HTMLResponse)
async def encounter_page(request: Request) -> HTMLResponse:
    return _render("encounter.html", request, {
        "patients": list_patients(),
        "active_tab": "encounter",
    })


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request) -> HTMLResponse:
    cfg = DemoConfig.from_env()
    audit_events: list[dict[str, Any]] = []
    error_msg: str | None = None

    if cfg.admin_secret:
        try:
            auth_resp = httpx.post(
                f"{cfg.broker_url}/v1/admin/auth",
                json={"secret": cfg.admin_secret},
                timeout=10,
            )
            auth_resp.raise_for_status()
            admin_token = auth_resp.json()["access_token"]

            events_resp = httpx.get(
                f"{cfg.broker_url}/v1/audit/events",
                params={"limit": 100},
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=10,
            )
            events_resp.raise_for_status()
            data = events_resp.json()
            audit_events = data.get("events", [])
        except Exception as e:
            error_msg = str(e)

    return _render("audit.html", request, {
        "events": audit_events,
        "error": error_msg,
        "active_tab": "audit",
    })


@router.get("/operator", response_class=HTMLResponse)
async def operator_page(request: Request) -> HTMLResponse:
    cfg = DemoConfig.from_env()
    health_data: dict[str, Any] = {}
    error_msg: str | None = None

    try:
        from agentauth import AgentAuthApp
        aa_app = AgentAuthApp(cfg.broker_url, cfg.client_id, cfg.client_secret)
        h = aa_app.health()
        health_data = {
            "status": h.status,
            "version": h.version,
            "uptime": h.uptime,
            "db_connected": h.db_connected,
            "audit_events_count": h.audit_events_count,
        }
        aa_app.close()
    except Exception as e:
        error_msg = str(e)

    from demo.config import APP_SCOPE_CEILING

    return _render("operator.html", request, {
        "health": health_data,
        "scope_ceiling": APP_SCOPE_CEILING,
        "error": error_msg,
        "active_tab": "operator",
    })
