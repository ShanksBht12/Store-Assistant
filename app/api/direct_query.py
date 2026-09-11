"""
direct_query.py — POST /api/ask endpoint.

Standalone "ask anything, get Markdown back" feature.
Completely separate from the sales-agent chat flow:
  - No tools, no DB queries, no conversation memory.
  - Uses the same LLMProvider abstraction as /api/chat.
  - Returns answer in Markdown at the requested length.
"""
from fastapi import APIRouter, HTTPException

from app.agent.direct_query import generate_direct_answer
from app.schemas.direct_query import DirectQueryRequest, DirectQueryResponse

router = APIRouter(tags=["Direct Query"])


@router.post("/api/ask", response_model=DirectQueryResponse)
async def ask(payload: DirectQueryRequest) -> DirectQueryResponse:
    """
    Answer any question directly via the LLM, formatted as Markdown.

    - No tool calls, no DB access, no conversation history.
    - Use `length` to control response size: short / medium / long.
    - Use `max_words` to set a precise word-count cap (overrides `length`).
    """
    try:
        answer_markdown, length_used = await generate_direct_answer(
            question  = payload.question,
            length    = payload.length,
            max_words = payload.max_words,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return DirectQueryResponse(
        answer_markdown = answer_markdown,
        length_used     = length_used,
    )
