from novaxis_core.settings import Settings
from novaxis_core.version import build_info


def test_settings_defaults_are_local() -> None:
    s = Settings(_env_file=None)
    assert s.env == "local"
    assert s.worker_enabled is True


def test_settings_read_prefixed_env(monkeypatch) -> None:
    monkeypatch.setenv("NOVAXIS_ENV", "staging")
    monkeypatch.setenv("NOVAXIS_WORKER_ENABLED", "false")
    s = Settings(_env_file=None)
    assert s.env == "staging"
    assert s.worker_enabled is False


def test_build_info_has_version_and_commit() -> None:
    info = build_info()
    assert set(info) == {"version", "commit"}
