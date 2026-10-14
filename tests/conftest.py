import pytest

import app as app_module


@pytest.fixture
def client():
    app_module.cached_translate.cache_clear()
    with app_module.app.test_client() as c:
        yield c