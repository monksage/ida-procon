from pydantic import BaseModel


class FunctionMeta(BaseModel):
    name: str
    addr: str
    size: str
    has_type: bool
    callees: list[dict]
    xrefs_to: list[dict]
    skip: bool
    file: str


class FunctionStatus(BaseModel):
    name: str
    status: str       # uncovered | resolved | skip
    size: str          # micro | func | precontour
    lines: int
    partof: list[str]


class FunctionEntry(BaseModel):
    """Candidate entry point returned by next-entry."""
    name: str
    size: str
    lines: int
    callees_count: int
    xrefs_count: int
    uncovered_callees: int  # how many callees are still uncovered


class ResolveRequest(BaseModel):
    module: str
    name: str
    contour: str
    role: str = "helper"  # entry | helper | leaf | micro
