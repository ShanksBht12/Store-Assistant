"""
prompts.py — Admin API for prompt version management.

Exposes:
  GET  /api/prompts                — list all prompt versions (newest first)
  GET  /api/prompts/active         — get the currently active prompt version
  POST /api/prompts                — create a new prompt version
  POST /api/prompts/{id}/activate  — activate a specific version (deactivates others)

HOW PROMPT VERSIONING WORKS:
  Every system prompt change is saved as a new row in prompt_versions.
  Exactly one row has is_active=1 — that is what the agent uses.
  The agent reads the active prompt fresh on each conversation turn via
  PromptRegistry.get_active_prompt(), so activating a new version takes
  effect immediately without a server restart.

DSPY INTEGRATION:
  When DSPy's BootstrapFewShot optimizes the prompt, the optimized
  instructions are saved as a new version via POST /api/prompts with
  created_by="dspy-bootstrap" and activate=true. The original version
  remains in the DB for rollback.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.prompt import PromptRegistry
from app.database.database import get_db
from app.database.models import PromptVersion
from app.schemas.prompt import PromptVersionCreate, PromptVersionList, PromptVersionOut

router = APIRouter(prefix="/api/prompts", tags=["Prompts"])


@router.get("", response_model=PromptVersionList)
def list_prompt_versions(db: Session = Depends(get_db)):
    """Return all prompt versions, newest first."""
    versions = (
        db.query(PromptVersion)
        .order_by(PromptVersion.version.desc())
        .all()
    )
    return PromptVersionList(total=len(versions), versions=versions)


@router.get("/active", response_model=PromptVersionOut)
def get_active_prompt(db: Session = Depends(get_db)):
    """Return the currently active prompt version."""
    row = (
        db.query(PromptVersion)
        .filter(PromptVersion.is_active == 1)
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No active prompt version found. Seed the initial version first.",
        )
    return row


@router.post("", response_model=PromptVersionOut, status_code=201)
def create_prompt_version(
    body: PromptVersionCreate,
    db: Session = Depends(get_db),
):
    """
    Save a new prompt version.

    If activate=true, this version becomes the active prompt immediately —
    the next chat request will use it.
    """
    new_pv = PromptRegistry.create_version(
        prompt_text=body.prompt_text,
        label=body.label,
        notes=body.notes,
        created_by=body.created_by,
        activate=body.activate,
        db=db,
    )
    return new_pv


@router.post("/{version_id}/activate", response_model=PromptVersionOut)
def activate_prompt_version(
    version_id: int,
    db: Session = Depends(get_db),
):
    """
    Activate a specific prompt version by its database ID.
    All other versions are deactivated.
    The agent picks up the change on the next request (no restart needed).
    """
    try:
        row = PromptRegistry.activate_version(version_id=version_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return row
