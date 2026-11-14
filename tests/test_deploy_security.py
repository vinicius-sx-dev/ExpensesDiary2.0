import asyncio
import secrets
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from test_security_finance import login

from app.config import Settings
from app.main import BodyLimit


def production(**changes):
    return Settings(_env_file=None, environment='production',
                    database_url='mysql+pymysql://app:placeholder@localhost/expenses',
                    jwt_secret=secrets.token_urlsafe(48), smtp_host='smtp.example.com',
                    smtp_from='app@example.com', smtp_user='app', smtp_password='placeholder',
                    **{'allowed_hosts': ['api.example.com'], 'cors_origins': ['https://app.example.com'], **changes})


def test_production_fails_closed():
    assert production().registration_enabled is False
    for changes in [{'allowed_hosts': ['*']}, {'allowed_hosts': ['localhost']},
                    {'allowed_hosts': []}, {'cors_origins': ['https://']},
                    {'cors_origins': ['https://a.example/path']},
                    {'cors_origins': ['https://user:pass@a.example']},
                    {'cors_origins': ['http://a.example']}]:
        with pytest.raises(ValidationError):
            production(**changes)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment='prod', database_url='sqlite://', jwt_secret='x' * 48)


def test_registration_switch(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'registration_enabled', False)
    assert client.post('/auth/register', json={
        'name': 'User', 'email': 'user@example.com', 'password': 'valid long password'
    }).status_code == 403


def test_cors_on_guard_errors(client):
    with patch('app.main.limit') as limiter:
        from fastapi import HTTPException
        limiter.side_effect = HTTPException(429, 'Limit', headers={'Retry-After': '60'})
        response = client.get('/health', headers={'Origin': 'http://localhost:8081'})
    assert response.status_code == 429
    assert response.headers['access-control-allow-origin'] == 'http://localhost:8081'
    assert response.headers['retry-after'] == '60'
    response = client.post('/auth/login', content=b'x' * 17000,
                           headers={'Origin': 'http://localhost:8081'})
    assert response.status_code == 413
    assert response.headers['access-control-allow-origin'] == 'http://localhost:8081'


def test_body_limit_streamed_and_timeout():
    async def scenario(chunks, timeout=False):
        sent = []
        called = []
        async def endpoint(scope, receive, send):
            called.append(await receive())
        async def receive():
            if timeout:
                raise TimeoutError
            return chunks.pop(0)
        async def send(message):
            sent.append(message)
        await BodyLimit(endpoint)({'type': 'http'}, receive, send)
        return sent, called
    sent, called = asyncio.run(scenario([
        {'type': 'http.request', 'body': b'x' * 9000, 'more_body': True},
        {'type': 'http.request', 'body': b'x' * 9000, 'more_body': False}]))
    assert sent[0]['status'] == 413 and not called
    sent, called = asyncio.run(scenario([], timeout=True))
    assert sent[0]['status'] == 408 and not called
    sent, called = asyncio.run(scenario([
        {'type': 'http.request', 'body': b'a', 'more_body': True},
        {'type': 'http.request', 'body': b'b', 'more_body': False}]))
    assert called[0]['body'] == b'ab'


def test_global_ai_quota_across_users(client, monkeypatch):
    from app import reports
    from app.security import limit
    monkeypatch.setattr(reports.settings, 'groq_api_key', 'test-only')
    monkeypatch.setattr(reports.settings, 'ai_global_hourly_limit', 1)
    a, _ = login(client)
    b, _ = login(client, 'bob@example.com')
    limit('ai-global', 'all', 1, 3600)
    with patch('app.reports.httpx.Client') as outbound:
        for headers in [a, b]:
            assert client.post('/reports/weekly/insights', headers=headers).status_code == 429
        outbound.assert_not_called()
