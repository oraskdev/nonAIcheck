import json
import re
from unittest.mock import patch
from xml.etree import ElementTree

from fastapi.testclient import TestClient
from app import public_pages
from app.main import app


def test_every_public_page_has_server_content_and_unique_metadata():
    titles, descriptions = set(), set()
    with patch.object(public_pages.settings, 'app_url', 'https://txtzi.example'):
        client = TestClient(app)
        for path in public_pages.PUBLIC_PATHS:
            result = client.get(path, headers={'host': 'attacker.example'})
            assert result.status_code == 200
            assert '<h1>' in result.text
            assert 'PUBLIC_' not in result.text
            assert f'<link rel="canonical" href="https://txtzi.example{path}">' in result.text
            assert 'attacker.example' not in result.text
            assert 'x-robots-tag' not in result.headers
            title = re.search(r'<title>(.*?)</title>', result.text).group(1)
            description = re.search(r'<meta name="description" content="(.*?)">', result.text).group(1)
            titles.add(title); descriptions.add(description)
            graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', result.text).group(1))['@graph']
            assert not any('aggregateRating' in entry or 'review' in entry for entry in graph)
            assert ('type="module"' in result.text) == (path == '/')
    assert len(titles) == len(public_pages.PUBLIC_PATHS)
    assert len(descriptions) == len(public_pages.PUBLIC_PATHS)


def test_prices_retention_and_payment_status_come_from_settings():
    with patch.multiple(public_pages.settings, base_price=512, extra_price=231, detector_price=147, ocr_price=37, slide_price=19, retention_hours=73, weekly_free_credits=325, stripe_key='', stripe_webhook=''):
        html = public_pages.render('/pricing')
        for value in ['$5.12', '$2.31', '$1.47', '$0.37', '$0.19', '$3.25']:
            assert value in html
        assert 'Card checkout is not available' in html
        assert '73 hours' in public_pages.render('/privacy')
        assert 'UTC' in html
    with patch.multiple(public_pages.settings, stripe_key='test', stripe_webhook='test', weekly_free_credits=0):
        html = public_pages.render('/pricing')
        assert 'Card checkout is connected' in html
        assert 'Weekly promotional credits are not enabled' in html


def test_sitemap_contains_real_public_paths_only_and_escapes_configured_origin():
    with patch.object(public_pages.settings, 'app_url', 'https://txtzi.example'):
        client = TestClient(app)
        result = client.get('/sitemap.xml')
        urls = [e.text for e in ElementTree.fromstring(result.text).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        assert set(urls) == {'https://txtzi.example' + p for p in public_pages.indexable_paths()}
        assert all('/api/' not in url and '#' not in url and '?' not in url for url in urls)
        assert all(client.get(url).status_code == 200 for url in urls)


def test_private_api_and_account_query_responses_are_not_indexable():
    client = TestClient(app)
    for path in ['/api/config', '/api/nonexistent', '/?reset=example#account', '/?setup=1', '/?checkout=success']:
        result = client.get(path)
        assert result.headers['x-robots-tag'] == 'noindex, nofollow'
        assert result.headers['cache-control'] == 'no-store'
    for path in ['/', '/about', '/pricing']:
        assert 'x-robots-tag' not in client.get(path).headers


def test_robots_search_agents_keep_private_exclusions():
    with patch.object(public_pages.settings, 'app_url', 'https://txtzi.example'):
        text = TestClient(app).get('/robots.txt').text
        assert 'Sitemap: https://txtzi.example/sitemap.xml' in text
        for agent in ['*', 'OAI-SearchBot', 'Bingbot']:
            group = text.split('User-agent: ' + agent + '\n', 1)[1].split('User-agent:')[0]
            assert 'Allow: /' in group
            assert 'Disallow: /api/' in group
            assert 'Disallow: /*?reset=' in group


def test_evidence_links_only_archived_tests_and_describes_limits():
    page = public_pages.render('/evidence')
    assert '61.61' in page and '46.18' in page
    assert '/static/research-ten-trials.html' in page
    assert 'held-out' in page
    assert 'research-under-ten' not in page and 'research-adaptive' not in page
    assert 'does not claim a below-30 or below-10 production result' in page
    cleanup = public_pages.render('/document-cleanup')
    assert 'Statistical text watermarks are not assessed' in cleanup
    assert 'U+FEFF' in cleanup and 'U+00AD' in cleanup and 'U+2060' in cleanup


def test_canonical_origin_rejects_credentials_or_non_origin_settings():
    for value in ['javascript:alert(1)', 'https://user:pass@example.com', 'https://example.com/path', 'https://example.com?x=1']:
        with patch.object(public_pages.settings, 'app_url', value):
            try:
                public_pages.origin()
            except ValueError:
                pass
            else:
                raise AssertionError(value)


def test_recovery_summary_keeps_research_separate_from_automatic_jobs():
    html = public_pages.render('/evidence')
    assert '23.18 / 100 with Desklib' in html and '14.44 / 100 with Vanguard' in html
    assert '2026-10-04T14:05:21Z' in html
    assert 'not 1,000 independent three-provider rewrites' in html
    assert '21 completed provider requests, plus one failed attempt' in html
    assert 'not what an ordinary app job runs' in html
    assert 'neither was held out' in html
    assert 'retained privately' in html
    assert '/blob/5a46f806a9897fc04feef8305a0ae1d0342fc5c5/docs/recovery-research-results-2026-10-04.md' in html
    assert '/tree/5a46f806a9897fc04feef8305a0ae1d0342fc5c5/scripts/research' in html
    assert '20.67' not in html and '12.17' not in html
    assert 'separate from the automatic app workflow' in public_pages.render('/')
