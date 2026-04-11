"""Selector Validation Request/Response Schemas"""

from pydantic import BaseModel, Field
from typing import Optional


class ValidateSelectorRequest(BaseModel):
    """Request to validate a single selector"""
    selector: str = Field(..., min_length=1, max_length=500)
    field_name: str = Field(..., min_length=1, max_length=100)


class ValidateSelectorResponse(BaseModel):
    """Response after validating a selector"""
    success: bool
    field_name: str
    selector: str
    match_count: int
    is_valid: bool
    sample_matches: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    error: Optional[str] = None
    status: str  # "working", "broken", "uncertain", "untested"
