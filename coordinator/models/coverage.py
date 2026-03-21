from pydantic import BaseModel


class CoverageNode(BaseModel):
    status: str       # uncovered | resolved | skip
    size: str          # micro | func | precontour
    lines: int
    partof: list[str]


class ModuleStatus(BaseModel):
    module: str
    total: int
    uncovered: int
    resolved: int
    skip: int
    claimed: int
    contours: int
