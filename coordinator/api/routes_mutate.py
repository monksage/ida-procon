"""
Mutation routes: claim, resolve, submit.
All writes go through the write queue.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.function import ResolveRequest
from models.contour import ContourSubmit

router = APIRouter()

# injected at startup
_registry = None
_claimer = None
_resolver = None
_contour_builder = None


def init(registry, claimer, resolver, contour_builder):
    global _registry, _claimer, _resolver, _contour_builder
    _registry = registry
    _claimer = claimer
    _resolver = resolver
    _contour_builder = contour_builder


class ClaimRequest(BaseModel):
    module: str
    name: str


class ClaimResponse(BaseModel):
    ok: bool
    reason: str = ""


class CodeUpdateRequest(BaseModel):
    module: str
    name: str
    code: str


@router.post("/claim")
def claim(req: ClaimRequest) -> ClaimResponse:
    mod = _registry.get_module(req.module)
    if mod is None:
        raise HTTPException(404, f"Module '{req.module}' not found")

    node = mod.get_coverage_node(req.name)
    if node is None:
        raise HTTPException(404, f"Function '{req.name}' not found")

    if node.get("status") == "resolved":
        return ClaimResponse(ok=False, reason="already_resolved")

    if node.get("status") == "skip":
        return ClaimResponse(ok=False, reason="skip")

    ok = _claimer.claim(req.module, req.name)
    if not ok:
        return ClaimResponse(ok=False, reason="already_claimed")

    return ClaimResponse(ok=True)


@router.post("/release")
def release(req: ClaimRequest) -> ClaimResponse:
    ok = _claimer.release(req.module, req.name)
    return ClaimResponse(ok=ok, reason="" if ok else "not_claimed")


@router.post("/resolve")
def resolve(req: ResolveRequest) -> dict:
    if req.role == "micro":
        ok = _resolver.resolve_micro(req.module, req.name, req.contour)
    else:
        ok = _resolver.resolve_func(req.module, req.name, req.contour, req.role)

    if not ok:
        raise HTTPException(400, "Failed to resolve")
    return {"ok": True}


@router.post("/update-code")
def update_code(req: CodeUpdateRequest) -> dict:
    ok = _resolver.update_func_code(req.module, req.name, req.code)
    if not ok:
        raise HTTPException(400, "Failed to update code")
    return {"ok": True}


@router.post("/submit-contour")
def submit_contour(contour: ContourSubmit) -> dict:
    ok = _contour_builder.submit(contour)
    if not ok:
        raise HTTPException(400, "Failed to submit contour")

    # release all claims for this contour's functions
    for func_name in contour.nodes:
        _claimer.release(contour.module, func_name)

    return {"ok": True, "name": contour.name}
