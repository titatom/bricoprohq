import os, importlib
from fastapi.testclient import TestClient


def make_client():
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test_m3_m6.db"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    from app import main
    importlib.reload(main)
    return TestClient(main.app)


def auth(client):
    token = client.post('/auth/login', json={'email':'admin@bricopro.local','password':'admin1234'}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_social_to_publishing_to_campaign_flow():
    c = make_client(); h = auth(c)
    gen = c.post('/social/generate', headers=h, json={
        'service_category':'Peinture intérieure','platform':'facebook','language':'fr','tone':'professional','job_description':'Mur salon','city':'Montreal','cta':'request_quote'
    })
    assert gen.status_code == 200
    draft_id = gen.json()['draft_id']

    move = c.put(f'/publishing/drafts/{draft_id}/status?status=needs_review', headers=h)
    assert move.status_code == 200

    camp = c.post('/campaigns', headers=h, json={'name':'Spring push','service_category':'Peinture','status':'active','message':'Book now'})
    assert camp.status_code == 200
    camp_id = camp.json()['id']

    camp_gen = c.post(f'/campaigns/{camp_id}/generate', headers=h)
    assert camp_gen.status_code == 200

    cal = c.get('/publishing/calendar', headers=h)
    assert cal.status_code == 200
