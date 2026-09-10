"""
registry_factory.py — Resolve the correct ToolRegistry for a tenant at request time.

WHY THIS EXISTS
  router.py used to hardcode RetailToolRegistry for every request. That meant
  switching a tenant to a different business type required a code change.

  build_registry(tenant) makes the router dynamic: it reads tenant.registry_type
  from the TenantContext (which comes from the tenant_configs DB row) and returns
  the matching ToolRegistry implementation. Changing a tenant's registry is now a
  database update — no code change, no restart.

ADDING A NEW BUSINESS TYPE
  1. Write app/agent/<type>_registry.py implementing the ToolRegistry Protocol.
  2. Import it here and add a branch: if registry_type == "<type>": return <Type>ToolRegistry(tenant)
  3. Insert or update the tenant row: UPDATE tenant_configs SET registry_type='<type>' WHERE tenant_id='...';
  That's all — router.py and agent.py stay completely unchanged.

CURRENT REGISTRY TYPES
  'retail'  → RetailToolRegistry  (product catalog, orders, stock, store info)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.agent.registry import ToolRegistry
from app.agent.retail_registry import RetailToolRegistry

if TYPE_CHECKING:
    from app.config import TenantContext

# Registry of known types. Add new entries here when new adapters are created.
# Maps the registry_type string (stored in tenant_configs.registry_type) to the
# concrete ToolRegistry class.
_REGISTRY_MAP: dict[str, type] = {
    "retail": RetailToolRegistry,
    # "agency": AgencyToolRegistry,   ← add future adapters here
    # "booking": BookingToolRegistry,
}


def build_registry(tenant: "TenantContext") -> ToolRegistry:
    """
    Instantiate and return the correct ToolRegistry for this tenant.

    Reads tenant.registry_type (sourced from tenant_configs.registry_type in the DB).
    Falls back to RetailToolRegistry if the value is missing or unrecognised,
    so existing tenants without the column set continue to work.

    Args:
        tenant: TenantContext resolved for the active request.

    Returns:
        A ToolRegistry instance configured for this tenant.

    Raises:
        ValueError: If registry_type is explicitly set to an unknown value.
                    (Unset/None falls back silently; an unknown explicit value
                    is likely a misconfiguration worth surfacing.)
    """
    registry_type = (tenant.registry_type or "retail").strip().lower()

    cls = _REGISTRY_MAP.get(registry_type)
    if cls is None:
        raise ValueError(
            f"Unknown registry_type '{registry_type}' for tenant '{tenant.tenant_id}'. "
            f"Supported types: {', '.join(sorted(_REGISTRY_MAP))}. "
            "Add the new adapter to registry_factory._REGISTRY_MAP."
        )

    return cls(tenant)
