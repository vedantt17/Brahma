"""Pydantic request/response contracts for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class InvestigationRequest(BaseModel):
    """Intake record. Mirrors a screening form: the subject may be an
    organization or an individual, and any field may be blank."""

    name: str = Field(..., min_length=2, max_length=400, examples=["Apple Inc."])
    entity_type: Literal["organization", "individual"] = "organization"
    country: str | None = Field(None, max_length=128, examples=["United States"])
    website: str | None = Field(None, max_length=512, examples=["https://apple.com"])
    address: str | None = Field(None, max_length=512)
    city: str | None = Field(None, max_length=128)
    # Individuals only. Accepts a full date or just a year; used to
    # corroborate or rule out an OFAC name hit.
    date_of_birth: str | None = Field(None, max_length=32, examples=["1963-02-05"])
    registration_number: str | None = Field(
        None, max_length=128, description="Company number, LEI, or national ID."
    )
    aliases: list[str] = Field(
        default_factory=list, max_length=20,
        description="Known trading names or alternate spellings.",
    )
    employer: str | None = Field(None, max_length=256, description="Reported employer or organization for a person.")
    profile_id: str | None = Field(None, pattern=r"^Q[1-9][0-9]*$", max_length=32,
                                 description="Public Wikidata human profile identifier; not identity verification.")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("profile_id", mode="before")
    @classmethod
    def normalize_profile_id(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class StrategyRequest(BaseModel):
    """A high-stakes business question for the executive decision board."""

    question: str = Field(
        ..., min_length=6, max_length=400,
        examples=["Should Salesforce acquire Notion?"],
    )

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        return value.strip() if isinstance(value, str) else value


class GraphInsightRequest(BaseModel):
    """Facts about one graph edge or node, for the AI insight agent."""

    kind: Literal["edge", "node"] = "edge"
    subject: str | None = None
    risk_level: str | None = None
    # edge
    source_label: str | None = None
    source_type: str | None = None
    target_label: str | None = None
    target_type: str | None = None
    relationship: str | None = None
    confidence: float | None = None
    description: str | None = None
    # node
    node_label: str | None = None
    node_type: str | None = None
    node_detail: str | None = None
    context: str | None = Field(None, max_length=2000)


class Supplier(BaseModel):
    name: str
    verified: bool
    status: str
    identity_confidence: float
    entity_type: str = "organization"
    country: str | None = None
    website: str | None = None
    lei: str | None = None
    cik: str | None = None
    registration_number: str | None = None
    aliases: list[str] = []
    primary_source: str | None = None


class InvestigationResponse(BaseModel):
    investigation_id: int | None = None
    query: dict[str, Any]
    supplier: Supplier
    entity_resolution: dict[str, Any]
    ownership: list[dict[str, Any]]
    sanctions: dict[str, Any]
    adverse_media: list[dict[str, Any]]
    recent_news: list[dict[str, Any]] = Field(default_factory=list)
    recent_news_summary: dict[str, Any] = Field(default_factory=dict)
    media_summary: dict[str, Any]
    litigation: dict[str, Any]
    transactions: dict[str, Any]
    graph: dict[str, Any]
    risk: dict[str, Any]
    evidence: list[dict[str, Any]]
    agent_summary: dict[str, Any]
    sources_consulted: dict[str, bool]
    optional_sources: dict[str, Any]
    duration_seconds: float
