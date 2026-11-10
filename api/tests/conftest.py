import pytest

# Tests must not depend on a developer's local configuration: ignore the repository .env
# (scripts/local-env.sh writes one for the local stack). Patched before the app is imported.
from atsurvey_api import config

config.Settings.model_config["env_file"] = None
config.get_settings.cache_clear()

from atsurvey_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _no_rate_limit():
    """Rate limiting is exercised explicitly in test_security.py; keep other tests independent."""
    limiter = app.state.rate_limiter
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous
