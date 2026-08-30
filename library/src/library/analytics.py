from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class OperationResult:
    success: bool = False
    error: int | None = None
    skip: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)
