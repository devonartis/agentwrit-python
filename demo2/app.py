"""AgentWrit Live — Support Ticket Zero-Trust Demo.

Flask app with HTMX + SSE. Three LLM-driven agents process support
tickets under broker-issued scoped credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, render_template, request, stream_with_context
from openai import OpenAI

from agentauth import AgentAuthApp

from demo2.config import APP_SCOPE_CEILING, DemoConfig
from demo2.data import QUICK_FILLS
from demo2.pipeline import run_pipeline

load_dotenv(Path(__file__).parent / ".env")

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)


def _get_app_and_llm() -> tuple[AgentAuthApp, OpenAI, str, str]:
    """Initialize SDK app and LLM client from env config."""
    cfg = DemoConfig.from_env()
    aa_app = AgentAuthApp(
        broker_url=cfg.broker_url,
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
    )
    llm_client = OpenAI(
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
    )
    return aa_app, llm_client, cfg.llm_model, cfg.broker_url


@app.route("/")
def index():
    return render_template("index.html",
                           quick_fills=QUICK_FILLS,
                           scope_ceiling=APP_SCOPE_CEILING)


@app.route("/api/run", methods=["POST"])
def run_ticket():
    """SSE endpoint — runs the pipeline and streams events."""
    ticket_text = request.form.get("ticket", "").strip()
    if not ticket_text:
        return Response("data: {\"error\": \"Empty ticket\"}\n\n",
                        content_type="text/event-stream")

    aa_app, llm_client, llm_model, broker_url = _get_app_and_llm()

    def generate():
        for event in run_pipeline(ticket_text, aa_app, llm_client, llm_model, broker_url):
            yield event.to_sse()

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/quick-fills")
def quick_fills():
    return QUICK_FILLS


if __name__ == "__main__":
    app.run(debug=True, port=5001)
