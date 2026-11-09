import pytest

from atsurvey_api.main import app


@pytest.fixture(autouse=True)
def _no_rate_limit():
    """Rate limiting is exercised explicitly in test_security.py; keep other tests independent."""
    limiter = app.state.rate_limiter
    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous
