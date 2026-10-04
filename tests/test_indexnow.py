from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from app import public_pages
from app.main import app
from scripts.submit_indexnow import payload, preflight


def test_preflight_accepts_only_live_canonical_public_pages():
    with patch.object(public_pages.settings, 'app_url', 'https://txtzi.onrender.com'):
        data = payload('https://txtzi.onrender.com')
        client = TestClient(app, base_url='https://txtzi.onrender.com')
        checked = preflight(client, data)
        assert checked == data['urlList']
        assert len(checked) == 10
        assert client.get('/static/index.html', follow_redirects=False).status_code == 308


def test_preflight_refuses_noindex_page_before_notification():
    data = payload('https://txtzi.onrender.com')
    requests = []
    def handle(request):
        requests.append(request.method)
        if request.url.path.endswith('.txt') and request.url.path != '/robots.txt':
            return httpx.Response(200, text=data['key'], headers={'content-type':'text/plain'})
        if request.url.path == '/sitemap.xml':
            with patch.object(public_pages.settings, 'app_url', 'https://txtzi.onrender.com'):
                return httpx.Response(200, text=public_pages.sitemap())
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nAllow: /\n')
        return httpx.Response(200, text='<link rel="canonical" href="https://txtzi.onrender.com/"><meta name="robots" content="noindex">', headers={'content-type':'text/html'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match='canonical or noindex'):
            preflight(client, data)
    assert set(requests) == {'GET'}


@pytest.mark.parametrize('origin', ['http://txtzi.onrender.com', 'https://localhost', 'https://127.0.0.1', 'https://user:password@txtzi.onrender.com', 'https://txtzi.onrender.com/path', 'https://txtzi.onrender.com?key=value'])
def test_notification_manifest_rejects_nonpublic_or_nonorigin_targets(origin):
    with pytest.raises(ValueError):
        payload(origin)
