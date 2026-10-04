#!/usr/bin/env python3
"""Offline by default. --check only reads. --submit preflights then sends one POST.

IndexNow acceptance acknowledges receipt; it never guarantees indexing or recommendation.
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import public_pages

ENDPOINT = 'https://api.indexnow.org/indexnow'


class PageSignals(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonicals = []
        self.noindex = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and attrs.get('rel', '').lower() == 'canonical':
            self.canonicals.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name', '').lower() in ('robots', 'bingbot'):
            self.noindex |= 'noindex' in attrs.get('content', '').lower()


def payload(origin):
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Use an HTTPS origin with no credentials, port, path, query or fragment.')
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('The submission origin must be a public hostname, not an IP address.')
    if host == 'localhost' or '.' not in host or host.endswith(('.localhost', '.local', '.test', '.example', '.invalid')):
        raise ValueError('The submission origin must be a public hostname.')
    base = f'https://{host}'
    return {'host': host, 'key': public_pages.INDEXNOW_KEY, 'keyLocation': base + '/' + public_pages.INDEXNOW_KEY + '.txt', 'urlList': [base + path for path in public_pages.indexable_paths()]}


def preflight(client, data):
    base = 'https://' + data['host']
    key = client.get(data['keyLocation'])
    key.raise_for_status()
    if key.status_code != 200 or key.text.strip() != data['key'] or not key.headers.get('content-type', '').startswith('text/plain'):
        raise ValueError('The live ownership key is not a matching plain-text response.')
    site = client.get(base + '/sitemap.xml'); site.raise_for_status()
    urls = {e.text for e in ElementTree.fromstring(site.text).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
    robot_response = client.get(base + '/robots.txt'); robot_response.raise_for_status()
    robots = RobotFileParser(); robots.parse(robot_response.text.splitlines())
    checked = []
    for url in data['urlList']:
        if url not in urls or not robots.can_fetch('Bingbot', url):
            raise ValueError('A submitted page is absent from the live sitemap or blocked by robots: ' + url)
        response = client.get(url); response.raise_for_status()
        if response.status_code != 200 or 'text/html' not in response.headers.get('content-type', ''):
            raise ValueError('A submitted page is not a direct HTML 200 response: ' + url)
        signals = PageSignals(); signals.feed(response.text)
        if signals.canonicals != [url] or signals.noindex or 'noindex' in response.headers.get('x-robots-tag', '').lower():
            raise ValueError('A submitted page has a mismatched canonical or noindex instruction: ' + url)
        checked.append(url)
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default=public_pages.settings.app_url)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--submit', action='store_true')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    data = payload(args.origin)
    result = {'mode': 'offline-preview', 'endpoint': ENDPOINT, 'payload': data, 'submitted': False}
    if args.check or args.submit:
        with httpx.Client(timeout=20, follow_redirects=False, headers={'User-Agent': 'txtzi-indexnow-preflight/1.0'}) as client:
            result['checked'] = preflight(client, data)
            result['mode'] = 'read-only-check'
            if args.submit:
                response = client.post(ENDPOINT, json=data)
                result.update(mode='submission', submitted=True, status_code=response.status_code, accepted=response.status_code in (200, 202), response=response.text[:1000], submitted_at=datetime.now(timezone.utc).isoformat(), notice='Receipt only; indexing and recommendations are not guaranteed.')
    encoded = json.dumps(result, indent=2)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(encoded + '\n')
    print(encoded)
    return 0 if not result['submitted'] or result['accepted'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, httpx.HTTPError, ElementTree.ParseError) as exc:
        print('IndexNow stopped: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
