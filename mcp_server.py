"""Brahma MCP server.

Exposes the Brahma investigate_supplier endpoint as an MCP tool so any
MCP-compatible agent (Claude Code, Codex, and others) can screen an entity and
receive the full evidence-backed intelligence object.

Run it:
    pip install "mcp[cli]" httpx
    BRAHMA_URL=http://127.0.0.1:8000 python mcp_server.py

ARGUS_URL remains supported for existing integrations.
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

BRAHMA_URL = (
    os.environ.get("BRAHMA_URL")
    or os.environ.get("ARGUS_URL")
    or "http://127.0.0.1:8000"
).rstrip("/")
ARGUS_URL = BRAHMA_URL  # Backwards-compatible module attribute.

mcp = FastMCP("Brahma")


@mcp.tool()
async def investigate_supplier(
    name: str,
    country: str = "",
    entity_type: str = "organization",
    date_of_birth: str = "",
) -> dict:
    """Investigate a supplier, company, or person for third-party risk.

    Screens the subject against OFAC sanctions, SEC EDGAR, GLEIF, GDELT adverse
    media, and CourtListener litigation, then returns one evidence-backed JSON
    object: resolved identity, sanctions result, tagged adverse media, ownership
    graph, and an explainable risk score with a recommendation.

    Args:
        name: Legal name of the company or full name of the person (required).
        country: Country, to sharpen entity resolution.
        entity_type: "organization" or "individual".
        date_of_birth: For individuals, to confirm or rule out an OFAC name hit.
    """
    payload = {"name": name, "entity_type": entity_type}
    if country:
        payload["country"] = country
    if date_of_birth:
        payload["date_of_birth"] = date_of_birth

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BRAHMA_URL}/api/v1/supplier/investigate", json=payload, timeout=180
        )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run()
