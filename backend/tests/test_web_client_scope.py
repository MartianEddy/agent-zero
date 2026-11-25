"""The investigations API answers only the web server and scopes cases to each browser.

Before this, production ran with one shared owner: anyone calling the public API, or
opening the web history, could list every case, including WhatsApp users' claims.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.investigations import models  # noqa: F401
from app.modules.investigations.routes import web_owner_for
from app.modules.investigations.service import DEV_USER_ID

SECRET = "proxy-secret-for-tests"
BROWSER_A = "a" * 43
BROWSER_B = "b" * 43


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def db():
        with factory() as session:
            yield session

    settings = SimpleNamespace(
        web_proxy_secret=SecretStr(SECRET),
        web_client_identity_key=SecretStr("identity-key"),
        app_env="development",
        auth_mode="disabled",
    )
    app.dependency_overrides[get_db] = db
    with patch("app.modules.investigations.routes.get_settings", return_value=settings):
        yield TestClient(app)
    app.dependency_overrides.clear()


def _headers(browser: str | None, secret: str | None = SECRET) -> dict[str, str]:
    headers = {}
    if secret is not None:
        headers["x-agent-zero-proxy"] = secret
    if browser is not None:
        headers["x-agent-zero-client"] = browser
    return headers


def _create(client, browser: str) -> dict:
    response = client.post(
        "/api/v1/investigations",
        json={"input_type": "TEXT", "content": "Nairobi is the capital of Kenya."},
        headers=_headers(browser),
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_direct_calls_without_the_proxy_secret_are_refused(client):
    assert client.get("/api/v1/investigations").status_code == 401
    wrong = _headers(BROWSER_A, "wrong")
    assert client.get("/api/v1/investigations", headers=wrong).status_code == 401
    assert client.get("/api/v1/investigations/history", headers=_headers(None)).status_code == 401
    assert client.get("/api/v1/investigations", headers=_headers("short")).status_code == 401


def test_each_browser_sees_only_its_own_cases(client):
    case = _create(client, BROWSER_A)

    mine = client.get("/api/v1/investigations", headers=_headers(BROWSER_A)).json()
    theirs = client.get("/api/v1/investigations", headers=_headers(BROWSER_B)).json()
    assert [item["id"] for item in mine] == [case["id"]]
    assert theirs == []

    other = _headers(BROWSER_B)
    assert client.get(f"/api/v1/investigations/{case['id']}", headers=other).status_code == 404
    reference = case["reference"]
    assert client.get(
        f"/api/v1/investigations/reference/{reference}", headers=other
    ).status_code == 404
    assert client.get(
        f"/api/v1/investigations/reference/{reference}", headers=_headers(BROWSER_A)
    ).status_code == 200


def test_web_owners_never_match_the_shared_whatsapp_owner():
    owners = {web_owner_for(token, "key") for token in (BROWSER_A, BROWSER_B)}
    assert len(owners) == 2
    assert DEV_USER_ID not in owners
    assert web_owner_for(BROWSER_A, "key") == web_owner_for(BROWSER_A, "key")


def test_health_check_does_not_need_the_proxy_secret(client):
    assert client.get("/api/v1/health").status_code == 200
