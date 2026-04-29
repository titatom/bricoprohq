import os
import importlib
from fastapi.testclient import TestClient


def make_client():
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test.db"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    from app import main
    importlib.reload(main)
    return TestClient(main.app)


def login(client):
    r = client.post('/auth/login', json={'email': 'admin@bricopro.local', 'password': 'admin1234'})
    token = r.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_dashboard_requires_auth():
    client = make_client()
    r = client.get('/dashboard')
    assert r.status_code == 401


def test_refresh_and_cache_flow():
    client = make_client()
    h = login(client)
    r = client.post('/dashboard/refresh/google_calendar', headers=h)
    assert r.status_code == 200
    r2 = client.get('/dashboard', headers=h)
    assert r2.status_code == 200
    payload = r2.json()
    assert payload['google_calendar']['cached'] is True
    assert 'data' in payload['google_calendar']
