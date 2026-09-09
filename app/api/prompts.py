"""
prompts.py — Admin API for prompt version management.

Exposes:
  GET  /api/prompts                — list prompt versions (filtered by tenant_id)
  GET  /api/prompts/active         — get the active prompt version for a tenant
  POST /api/prompts                — create a new prompt version for a tenant
  POST /api/prompts/{id}/activate  — activate a specific version (only affects its tenant)

HOW MULTI-TENANT PROMPT VERSIONING WORKS:
  Every prompt version is scoped to a tenant_id. Exactly one row per tenant
  has is_active=1 — that is what the agent uses for that tenant. Activating
  a version for one tenant has zero effect on any other tenant's active prompt.

  The agent reads the active prompt for its tenant fresh on each conversation
  turn via PromptRegistry.get_active_prompt_for_tenant(tenant), so changes
  take effect immediately without a server restart.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agent.prompt import PromptRegistry
from app.database.database import get_db
from app.database.models import PromptVersion
from app.schemas.prompt import PromptVersionCreate, PromptVersionList, PromptVersionOut

router = APIRouter(prefix="/api/prompts", tags=["Prompts"])


@router.get("", response_model=PromptVersionList)
def list_prompt_versions(
    tenant_id: str = Query(default="default", description="Filter versions by tenant"),
    db: Session = Depends(get_db),
):
    """Return all prompt versions for a tenant, newest first."""
    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.tenant_id == tenant_id)
        .order_by(PromptVersion.version.desc())
        .all()
    )
    return PromptVersionList(total=len(versions), versions=versions)


@router.get("/active", response_model=PromptVersionOut)
def get_active_prompt(
    tenant_id: str = Query(default="default", description="Tenant to get active prompt for"),
    db: Session = Depends(get_db),
):
    """Return the currently active prompt version for the given tenant."""
    row = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.tenant_id == tenant_id,
            PromptVersion.is_active == 1,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active prompt version found for tenant '{tenant_id}'.",
        )
    return row


@router.post("", response_model=PromptVersionOut, status_code=201)
def create_prompt_version(
    body: PromptVersionCreate,
    db: Session = Depends(get_db),
):
    """
    Save a new prompt version for a tenant.
    If activate=true, this version becomes the active prompt for that tenant
    immediately — other tenants are unaffected.
    """
    new_pv = PromptRegistry.create_version(
        prompt_text=body.prompt_text,
        label=body.label,
        notes=body.notes,
        created_by=body.created_by,
        activate=body.activate,
        tenant_id=body.tenant_id,
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
    Only deactivates other versions for the same tenant — other tenants
    are unaffected. The agent picks up the change on the next request.
    """
    try:
        row = PromptRegistry.activate_version(version_id=version_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return row
