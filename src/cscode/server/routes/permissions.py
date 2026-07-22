from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cscode.core.permission_v2 import Rule, RuleEffect, SavedRules
from cscode.server.state import state
from cscode.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


class PermissionRuleCreate(BaseModel):
    action: str
    resource: str
    effect: str = "allow"


class PermissionRuleUpdate(BaseModel):
    action: str | None = None
    resource: str | None = None
    effect: str | None = None


def _db_or_503() -> SavedRules:
    if state.db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    return SavedRules(state.db)


_RULE_EFFECTS = {"allow": RuleEffect.ALLOW, "deny": RuleEffect.DENY}


def _parse_effect(effect: str, field: str = "effect") -> RuleEffect:
    try:
        return _RULE_EFFECTS[effect.lower()]
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=f"{field}: must be 'allow' or 'deny', got '{effect}'",
        )


def _rule_to_dict(rule_id: int, rule: Rule) -> dict[str, object]:
    return {
        "id": rule_id,
        "action": rule.action,
        "resource": rule.resource,
        "effect": rule.effect.value,
    }


@router.get("/permission-rules")
async def list_permission_rules() -> list[dict[str, object]]:
    """List all saved permission rules."""
    saved = _db_or_503()
    return await saved.list_all()


@router.post("/permission-rules")
async def create_permission_rule(rule: PermissionRuleCreate) -> dict[str, object]:
    """Create a new permission rule."""
    saved = _db_or_503()
    effect = _parse_effect(rule.effect)
    r = Rule(action=rule.action, resource=rule.resource, effect=effect)
    rule_id = await saved.save(r)
    return _rule_to_dict(rule_id, r)


@router.delete("/permission-rules/{rule_id:int}")
async def delete_permission_rule(rule_id: int) -> dict[str, str]:
    """Delete a permission rule by its numeric id."""
    saved = _db_or_503()
    try:
        await saved.delete_by_id(rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "ok"}


@router.put("/permission-rules/{rule_id:int}")
async def update_permission_rule(
    rule_id: int, update: PermissionRuleUpdate
) -> dict[str, object]:
    """Update fields of an existing permission rule."""
    saved = _db_or_503()

    effect: RuleEffect | None = None
    if update.effect is not None:
        effect = _parse_effect(update.effect, "effect")

    try:
        await saved.update(
            rule_id,
            action=update.action,
            resource=update.resource,
            effect=effect,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Return updated rule — read it back via list_all
    for entry in await saved.list_all():
        if entry["id"] == rule_id:
            return entry
    raise HTTPException(status_code=500, detail="Rule not found after update")
