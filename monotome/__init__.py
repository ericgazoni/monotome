import dataclasses
import enum
from copy import deepcopy
from pathlib import Path


class AppliedStatus(enum.Enum):
    applied = enum.auto()
    unapplied = enum.auto()
    conflict = enum.auto()


@dataclasses.dataclass
class Page:
    id: str
    stack: str
    feature: str
    checksum: str

    def __hash__(self) -> int:
        return hash((self.id, self.checksum))

    def __eq__(self, other) -> bool:
        return hash(self) == hash(other)


@dataclasses.dataclass
class MigrationPage(Page):
    full_path: Path
    content: str
    requires: list
    status: AppliedStatus = AppliedStatus.unapplied

    def __hash__(self) -> int:
        return hash((self.id, self.checksum))

    def __eq__(self, other) -> bool:
        return hash(self) == hash(other)

    def clone(self):
        return deepcopy(self)


from .migrations import (
    get_all_migrations,
    apply_migrations,
    write_lockfile,
    assert_lockfile_consistency,
)  # noqa

__all__ = [
    "get_all_migrations",
    "apply_migrations",
    "write_lockfile",
    "assert_lockfile_consistency",
]
