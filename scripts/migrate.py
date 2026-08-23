from alembic import command
from alembic.config import Config
from pathlib import Path

from backend.app.config import ensure_database_directory, get_settings


def main() -> None:
    ensure_database_directory(get_settings())
    root = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(root / "alembic.ini")), "head")


if __name__ == "__main__":
    main()
