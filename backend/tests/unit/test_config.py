from pathlib import Path

from backend.app.config import (
    AppSettings,
    ensure_database_directory,
    ensure_runtime_directories,
    get_settings,
    public_settings,
)


def test_yaml_load_and_environment_override(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "app:\n  port: 9000\nbangumi:\n  access_token: secret-from-yaml\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTOANIME_CONFIG", str(config))
    monkeypatch.setenv("AUTOANIME_APP__PORT", "9100")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app.port == 9100
    assert settings.bangumi.access_token.get_secret_value() == "secret-from-yaml"
    assert public_settings(settings)["bangumi"]["access_token"] == "***"
    get_settings.cache_clear()


def test_runtime_setup_does_not_create_missing_external_library_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    database = tmp_path / "nested" / "database" / "autoanime.db"
    missing_library = tmp_path / "external-media-not-mounted"
    settings = AppSettings(
        database={"url": f"sqlite:///{database}"},
        storage={"library_roots": [missing_library]},
    )

    ensure_database_directory(settings)
    ensure_runtime_directories(settings)

    assert database.parent.is_dir()
    assert not missing_library.exists()
