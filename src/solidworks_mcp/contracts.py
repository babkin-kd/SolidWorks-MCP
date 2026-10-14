"""Shared application v2 response schema, advertised through MCP outputSchema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra='allow')
    code: str
    message: str


class ResponseEnvelope(BaseModel):
    status: Literal['queued', 'running', 'succeeded', 'failed', 'cancelled', 'unknown']
    operation_id: str | None
    context: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] | None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    error: ErrorDetail | None
