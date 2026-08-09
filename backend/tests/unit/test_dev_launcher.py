from argparse import Namespace
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("autoanime_dev_launcher", ROOT / "scripts" / "dev.py")
assert SPEC is not None and SPEC.loader is not None
DEV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEV)
desktop_command = DEV.desktop_command
parse_args = DEV.parse_args
project_python = DEV.project_python
migrate_database = DEV.migrate_database


def test_desktop_command_defaults_to_native_qml_client() -> None:
    root = Path("/project")

    assert desktop_command(root, parse_args([])) == [
        "/project/desktop/build/autoanime-desktop",
    ]


def test_desktop_command_forwards_episode() -> None:
    args = Namespace(no_build=True, play_episode=968)

    assert desktop_command(Path("/project"), args) == [
        "/project/desktop/build/autoanime-desktop",
        "--play-episode",
        "968",
    ]


def test_project_python_prefers_repository_virtualenv(tmp_path: Path) -> None:
    interpreter = tmp_path / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()

    assert project_python(tmp_path) == str(interpreter)


def test_migrate_database_uses_repository_python(tmp_path: Path, monkeypatch) -> None:
    interpreter = tmp_path / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    calls = []
    monkeypatch.setattr(DEV.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    migrate_database(tmp_path)

    assert calls == [(([str(interpreter), "-m", "scripts.migrate"],), {"cwd": tmp_path, "check": True})]
