import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_needs_no_login_and_checks_database():
    res = APIClient().get("/api/health/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": True}
