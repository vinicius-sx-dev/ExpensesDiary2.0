from cryptography.fernet import Fernet
from app.config import settings
from test_security_finance import login


def test_sync_isolated_idempotent_and_minimized(client, monkeypatch):
    monkeypatch.setattr(settings, "pluggy_mock_enabled", True)
    monkeypatch.setattr(settings, "statement_encryption_key", Fernet.generate_key().decode())
    assert client.post('/pluggy/mock/sync', json={}).status_code == 401
    a, _ = login(client)
    b, _ = login(client, 'bob@example.com')
    first = client.post('/pluggy/mock/sync', json={}, headers=a)
    assert first.status_code == 200, first.text
    assert first.json() == {'mode': 'mock', 'imported': 3, 'already_imported': 0, 'awaiting_goal': 1}
    assert client.post('/pluggy/mock/sync', json={}, headers=a).json()['already_imported'] == 3
    assert client.get('/entries', headers=b).json() == []
    rows = client.get('/entries', headers=a).json()
    assert all(r['description'] == '' for r in rows)
    assert client.delete('/entries/' + str(rows[0]['id']), headers=a).status_code == 204
    assert client.post('/pluggy/mock/sync', json={}, headers=a).json()['imported'] == 0
    assert client.post('/pluggy/mock/sync', json={'user_id': 2}, headers=a).status_code == 422
    assert client.post('/pluggy/mock/sync', json={'investment_goal_id': 999}, headers=a).status_code == 404


def test_mock_disabled_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, 'environment', 'production')
    monkeypatch.setattr(settings, 'pluggy_mock_enabled', True)
    assert client.post('/pluggy/mock/sync', json={}).status_code == 503
