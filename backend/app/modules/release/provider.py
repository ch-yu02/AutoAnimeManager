from __future__ import annotations

from typing import Protocol

from backend.app.modules.release.schemas import RawRelease


class ReleaseProviderError(RuntimeError):
    pass


class ReleaseProvider(Protocol):
    name: str

    async def search(
        self,
        subject_names: list[str],
        episode_number: float | None,
    ) -> list[RawRelease]: ...
