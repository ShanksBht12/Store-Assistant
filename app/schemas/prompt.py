"""
schemas/prompt.py — Pydantic models for the prompt versioning API.

  PromptVersionOut    — single prompt version returned by the API
  PromptVersionCreate — request body for creating a new prompt version
  PromptVersionList   — paginated list of prompt versions
"""
from datetime import datetime

from pydantic import BaseModel, Field


class PromptVersionOut(BaseModel):
    id:          int
    tenant_id:   str
    version:     int
    label:       str
    prompt_text: str
    notes:       str | None
    is_active:   int        # 1 = active for this tenant, 0 = inactive
    created_by:  str | None
    created_at:  datetime | None

    class Config:
        from_attributes = True


class PromptVersionCreate(BaseModel):
    prompt_text: str  = Field(..., min_length=10,  description="Full system prompt text (may contain {{ slots }})")
    label:       str  = Field("",                  description="Short version name, e.g. 'v3-dspy-optimized'")
    notes:       str  = Field("",                  description="Description of what changed")
    created_by:  str  = Field("admin",             description="Who/what created this version")
    activate:    bool = Field(False,               description="If true, activate this version for its tenant immediately")
    tenant_id:   str  = Field("default",           description="Which tenant this prompt version belongs to")


class PromptVersionList(BaseModel):
    total:    int
    versions: list[PromptVersionOut]
