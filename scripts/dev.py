from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


BACKEND_URL = "http://127.0.0.1:8765"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 AutoAnime 完整开发环境")
    parser.add_argument("--no-build", action="store_true", help="跳过 Qt Desktop 增量构建")
    parser.add_argument("--play-episode", type=int, help="启动后直接播放指定 Episode")
    return parser.parse_args(argv)


def desktop_command(root: Path, args: argparse.Namespace) -> list[str]:
    command = [str(root / "desktop" / "build" / "autoanime-desktop")]
    if args.play_episode:
        command.extend(["--play-episode", str(args.play_episode)])
    return command


def project_python(root: Path) -> str:
    candidates = (
        [root / ".venv" / "Scripts" / "python.exe"]
        if os.name == "nt"
        else [root / ".venv" / "bin" / "python"]
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def build_desktop(root: Path) -> None:
    print("[AutoAnime] 配置 Qt Desktop……", flush=True)
    subprocess.run(
        [
            "cmake",
            "-S",
            "desktop",
            "-B",
            "desktop/build",
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
        ],
        cwd=root,
        check=True,
    )
    print("[AutoAnime] 增量构建 Qt Desktop……", flush=True)
    subprocess.run(
        ["cmake", "--build", "desktop/build", "--target", "autoanime-desktop"],
        cwd=root,
        check=True,
    )


def start_process(command: list[str], root: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        cwd=root,
        start_new_session=os.name != "nt",
    )


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return


def kill_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def wait_for_http(
    url: str,
    processes: dict[str, subprocess.Popen[bytes]],
    timeout_seconds: float = 30,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for name, process in processes.items():
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"{name} 提前退出，状态码 {code}")
        try:
            with urlopen(url, timeout=0.5) as response:
                if response.status < 500:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise TimeoutError(f"等待服务超时：{url}")


def shutdown(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    for process in reversed(list(processes.values())):
        stop_process(process)
    deadline = time.monotonic() + 5
    for process in reversed(list(processes.values())):
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            kill_process(process)
            process.wait()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    executable = root / "desktop" / "build" / "autoanime-desktop"
    if not args.no_build:
        try:
            build_desktop(root)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"[AutoAnime] Qt Desktop 构建失败：{exc}", file=sys.stderr)
            return 1
    if not executable.is_file():
        print("[AutoAnime] 找不到 desktop/build/autoanime-desktop，请取消 --no-build 后重试。", file=sys.stderr)
        return 1

    processes: dict[str, subprocess.Popen[bytes]] = {}
    interrupted = False

    def request_stop(*_: object) -> None:
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        print("[AutoAnime] 启动 FastAPI……", flush=True)
        processes["FastAPI"] = start_process(
            [project_python(root), "-m", "uvicorn", "backend.app.main:app", "--reload", "--port", "8765"],
            root,
        )
        wait_for_http(f"{BACKEND_URL}/api/health", processes)
        if interrupted:
            return 130

        print("[AutoAnime] 服务已就绪，启动 Qt Desktop。关闭窗口即可全部退出。", flush=True)
        processes["Qt Desktop"] = start_process(desktop_command(root, args), root)
        while not interrupted:
            desktop_code = processes["Qt Desktop"].poll()
            if desktop_code is not None:
                return desktop_code
            for name in ("FastAPI",):
                code = processes[name].poll()
                if code is not None:
                    raise RuntimeError(f"{name} 意外退出，状态码 {code}")
            time.sleep(0.2)
        return 130
    except (OSError, RuntimeError, TimeoutError) as exc:
        print(f"[AutoAnime] 启动失败：{exc}", file=sys.stderr)
        return 1
    finally:
        shutdown(processes)


if __name__ == "__main__":
    raise SystemExit(main())
