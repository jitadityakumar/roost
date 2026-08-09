from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.standards import store

router = APIRouter(prefix="/api/standards/rules", tags=["standards"])


class CreateRuleRequest(BaseModel):
    field: str
    operator: str
    value: str


class PatchRuleRequest(BaseModel):
    field: str | None = None
    operator: str | None = None
    value: str | None = None
    enabled: bool | None = None


@router.get("")
def list_rules():
    return store.list_rules()


@router.post("", status_code=201)
def create_rule(body: CreateRuleRequest):
    try:
        return store.create_rule(body.field, body.operator, body.value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.patch("/{rule_id}")
def patch_rule(rule_id: int, body: PatchRuleRequest):
    changes = body.model_dump(exclude_unset=True)
    try:
        updated = store.update_rule(rule_id, **changes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="rule not found")
    return updated


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int):
    store.delete_rule(rule_id)
