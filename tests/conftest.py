import os

import pytest

from astro_api.settings import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRO_API_KEY", os.environ.get("ASTRO_API_KEY", "test-secret"))
    get_settings.cache_clear()
