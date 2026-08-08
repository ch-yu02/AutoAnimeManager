from dataclasses import dataclass


@dataclass
class SchedulerSkeleton:
    """阶段 0 调度器骨架；不注册或运行任何自动任务。"""

    enabled: bool = False
    running: bool = False

    def start(self) -> None:
        self.running = self.enabled

    def stop(self) -> None:
        self.running = False

    def status(self) -> dict[str, bool | int]:
        return {"enabled": self.enabled, "running": self.running, "jobs": 0}
