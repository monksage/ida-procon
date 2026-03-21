from pydantic import BaseModel


class ContourNode(BaseModel):
    role: str  # entry | helper | leaf | micro
    resolved_file: str
    description: str = ""


class ContourSubmit(BaseModel):
    module: str
    name: str  # e.g. "spline_fit@sub_662CE740"
    soldier: str  # "opus" | "sonnet"
    entry: str
    nodes: dict[str, ContourNode]
    edges: list[list[str]]
    external_deps: list[dict] = []
    summary: str = ""
