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


def test_desktop_command_defaults_to_integrated_development_mode() -> None:
    root = Path("/project")

    assert desktop_command(root, parse_args([])) == [
        "/project/desktop/build/autoanime-desktop",
        "--dev",
    ]


def test_desktop_command_forwards_optional_modes() -> None:
    args = Namespace(no_build=True, devtools=True, dedicated_player=True)

    assert desktop_command(Path("/project"), args) == [
        "/project/desktop/build/autoanime-desktop",
        "--dev",
        "--devtools",
        "--dedicated-player",
    ]
