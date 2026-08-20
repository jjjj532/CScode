from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cscode.core.permission_v2 import ReplyMode, Rule, RuleEffect, SavedRules, SessionPermission
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


class PermissionReply(BaseModel):
    mode: str


def _db_or_503() -> SavedRules:
    if state.db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    return SavedRules(state.db)


def _permission_or_503() -> SessionPermission:
    """Return the shared SessionPermission instance (queue survives requests)."""
    if state.db is None:
        raise HTTPException(status_code=503, detail="Server not initialized")
    if state.permission_manager is None:
        state.permission_manager = SessionPermission(SavedRules(state.db))
    return state.permission_manager


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


# ─── Pending request queue (spec §5.3) ────────────────────────────


@router.get("/permission/request")
async def list_pending_requests() -> list[dict[str, object]]:
    """List queued permission requests awaiting a user reply."""
    perms = _permission_or_503()
    requests = await perms.list_pending()
    return [
        {
            "request_id": r.request_id,
            "session_id": r.session_id,
            "action": r.action,
            "resource": r.resource,
        }
        for r in requests
    ]


@router.post("/permission/request/{request_id}/reply")
async def reply_permission_request(
    request_id: str, body: PermissionReply
) -> dict[str, object]:
    """Resolve a pending request: once / always / reject."""
    try:
        mode = ReplyMode(body.mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"mode: must be 'once', 'always' or 'reject', got '{body.mode}'",
        )
    perms = _permission_or_503()
    ok = await perms.reply(request_id, mode)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
    return {"status": "ok", "request_id": request_id, "mode": mode.value}
