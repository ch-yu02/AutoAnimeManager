from backend.app.modules.scheduler import SchedulerSkeleton


def test_scheduler_has_no_jobs_in_phase_zero() -> None:
    scheduler = SchedulerSkeleton(enabled=False)
    scheduler.start()

    assert scheduler.status() == {"enabled": False, "running": False, "jobs": 0}
