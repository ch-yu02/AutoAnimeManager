from __future__ import annotations

from backend.app.config import ensure_runtime_directories, get_settings
from backend.app.modules.maintenance import MaintenanceService


def main() -> None:
    settings = get_settings()
    ensure_runtime_directories(settings)
    result = MaintenanceService().create_backup()
    print(f"备份已创建并验证：{result['path']}")


if __name__ == "__main__":
    main()
