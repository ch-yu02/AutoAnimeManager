from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import ensure_runtime_directories, get_settings


def main() -> None:
    settings = get_settings()
    ensure_runtime_directories(settings)
    prefix = "sqlite:///"
    source_path = Path(settings.database.url.removeprefix(prefix))
    if not source_path.exists():
        raise SystemExit(f"数据库不存在：{source_path}")

    destination = Path("data/backups") / f"autoanime-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    print(f"备份已创建：{destination}")


if __name__ == "__main__":
    main()
