"""
schemas/direct_query.py — Request/response models for POST /api/ask.
"""
from typing import Literal

from pydantic import BaseModel, Field


class DirectQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000,
                          description="The question to answer.")
    length: Literal["short", "medium", "long"] = Field(
        default="medium",
        description=(
            "Desired response length. "
            "'short' = 2-3 sentences, "
            "'medium' = 1-2 paragraphs, "
            "'long' = thorough with headings/bullets."
        ),
    )
    max_words: int | None = Field(
        default=None,
        ge=10,
        le=2000,
        description=(
            "Optional hard word-count cap. "
            "When set, overrides the length preset."
        ),
    )


class DirectQueryResponse(BaseModel):
    answer_markdown: str = Field(
        description="The LLM's answer, formatted as Markdown."
    )
    length_used: str = Field(
        description="The effective length instruction that was applied."
    )
