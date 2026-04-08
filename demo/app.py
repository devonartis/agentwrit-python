"""MedAssist AI — AgentAuth Healthcare Demo.

FastAPI app that demonstrates the AgentAuth Python SDK through a
realistic healthcare multi-agent pipeline with clinical, prescription,
and billing agents operating under strict scope isolation.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from demo.routes.api import router as api_router
from demo.routes.pages import router as pages_router

# Load .env from demo directory
load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(
    title="MedAssist AI — AgentAuth Demo",
    description="Healthcare multi-agent demo showcasing AgentAuth scope isolation",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory="demo/static"), name="static")

app.include_router(pages_router)
app.include_router(api_router)
