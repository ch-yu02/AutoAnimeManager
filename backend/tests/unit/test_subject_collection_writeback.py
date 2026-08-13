from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config import get_settings
from backend.app.database.models import Subject
from backend.app.database.session import create_schema, get_engine, session_scope
from backend.app.modules.bangumi.errors import BangumiTemporaryError
from backend.app.modules.playback import writeback


class FakeBangumiClient:
    calls: list[tuple[int, str]] = []
    fail = False

    def __init__(self, _settings) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        pass

    async def set_subject_collection(self, subject_id: int, collection_type: str) -> None:
        self.calls.append((subject_id, collection_type))
        if self.fail:
            raise BangumiTemporaryError("temporary")


def _prepare(tmp_path: Path, monkeypatch) -> int:
    monkeypatch.setenv("AUTOANIME_DATABASE__URL", f"sqlite:///{tmp_path / 'writeback.db'}")
    monkeypatch.setenv("AUTOANIME_BANGUMI__ACCESS_TOKEN", "token")
    get_settings.cache_clear()
    get_engine.cache_clear()
    create_schema()
    FakeBangumiClient.calls = []
    FakeBangumiClient.fail = False
    monkeypatch.setattr(writeback, "BangumiClient", FakeBangumiClient)
    with session_scope() as session:
        subject = Subject(
            bangumi_subject_id=123,
            name="Anime",
            collection_type="WISH",
        )
        session.add(subject)
        session.flush()
        return subject.id


@pytest.mark.anyio
async def test_subject_collection_updates_remote_before_local(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id = _prepare(tmp_path, monkeypatch)

    result = await writeback.writeback_subject_collection(subject_id, "doing")

    assert FakeBangumiClient.calls == [(123, "DOING")]
    assert result["synced_to_bangumi"] is True
    with session_scope() as session:
        subject = session.get(Subject, subject_id)
        assert subject is not None
        assert subject.collection_type == "DOING"
        assert subject.collection_updated_at is not None


@pytest.mark.anyio
async def test_subject_collection_remote_failure_preserves_local_state(
    tmp_path: Path, monkeypatch
) -> None:
    subject_id = _prepare(tmp_path, monkeypatch)
    FakeBangumiClient.fail = True

    with pytest.raises(BangumiTemporaryError):
        await writeback.writeback_subject_collection(subject_id, "DROPPED")

    with session_scope() as session:
        subject = session.get(Subject, subject_id)
        assert subject is not None
        assert subject.collection_type == "WISH"
