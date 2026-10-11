"""Independent news fallback must preserve availability and evidence origin."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock
from xml.sax.saxutils import escape

import pytest

from app.sources import gdelt, news, news_rss


def rss(items):
    return '<rss version="2.0"><channel>' + ''.join(
        '<item><title>' + escape(title + ' - Example News') + '</title>'
        '<link>https://news.google.com/rss/articles/' + str(index) + '</link>'
        '<pubDate>' + format_datetime(date) + '</pubDate>'
        '<source url="https://example.com">Example News</source></item>'
        for index, (title, date) in enumerate(items)) + '</channel></rss>'


def test_rss_parses_recent_relevant_adverse_headlines_and_deduplicates(monkeypatch):
    now = datetime.now(timezone.utc)
    body = rss([
        ('Anthropic faces copyright lawsuit', now),
        ('Anthropic faces copyright lawsuit', now),
        ('Other company faces lawsuit', now),
        ('Anthropic launches Claude', now),
        ('Anthropic settled lawsuit', now - timedelta(days=200)),
    ])
    fetch = AsyncMock(return_value=body)
    monkeypatch.setattr(news_rss, 'fetch', fetch)
    result = asyncio.run(news_rss.search('Anthropic, PBC'))
    assert len(result) == 1
    assert result[0]['title'] == 'Anthropic faces copyright lawsuit'
    assert result[0]['source'] == 'Example News'
    assert result[0]['provider'] == 'Google News RSS'
    assert result[0]['body'] is None
    assert result.search_metadata['raw_count'] == 5
    assert fetch.call_args.args[0] == news_rss.SEARCH_URL
    assert fetch.call_args.kwargs['params']['q'].startswith('"Anthropic" ')


@pytest.mark.parametrize('body', [None, '<html>blocked</html>', '<rss>',
                                '<!DOCTYPE rss><rss><channel/></rss>'])
def test_invalid_rss_is_unavailable_not_an_empty_success(monkeypatch, body):
    monkeypatch.setattr(news_rss, 'fetch', AsyncMock(return_value=body))
    with pytest.raises(RuntimeError):
        asyncio.run(news_rss.search('Anthropic'))


def test_primary_failure_uses_independent_feed_without_claiming_gdelt_success(monkeypatch):
    monkeypatch.setattr(gdelt, 'search', AsyncMock(side_effect=RuntimeError('503')))
    monkeypatch.setattr(news_rss, 'fetch', AsyncMock(return_value=rss([
        ('Anthropic faces copyright lawsuit', datetime.now(timezone.utc))])))
    result = asyncio.run(news.search('Anthropic'))
    assert len(result) == 1
    assert result.search_metadata['providers'] == {'gdelt': False, 'google_news': True}
    assert result.search_metadata['fallback'] is True


def test_healthy_primary_does_not_request_fallback(monkeypatch):
    primary = gdelt.MediaResults([{'title': 'Anthropic lawsuit'}], {'raw_count': 1})
    monkeypatch.setattr(gdelt, 'search', AsyncMock(return_value=primary))
    fallback = AsyncMock()
    monkeypatch.setattr(news_rss, 'search', fallback)
    result = asyncio.run(news.search('Anthropic'))
    assert result == primary
    assert result.search_metadata['providers'] == {'gdelt': True}
    fallback.assert_not_called()


def test_both_provider_failures_remain_explicit(monkeypatch):
    monkeypatch.setattr(gdelt, 'search', AsyncMock(side_effect=RuntimeError('503')))
    monkeypatch.setattr(news_rss, 'search', AsyncMock(side_effect=RuntimeError('blocked')))
    result = asyncio.run(news.search('Anthropic'))
    assert result == []
    assert not any(result.search_metadata['providers'].values())


def test_empty_healthy_primary_survives_fallback_failure(monkeypatch):
    monkeypatch.setattr(gdelt, 'search', AsyncMock(return_value=gdelt.MediaResults([], {'raw_count': 0})))
    monkeypatch.setattr(news_rss, 'search', AsyncMock(side_effect=RuntimeError('blocked')))
    result = asyncio.run(news.search('Anthropic'))
    assert result == []
    assert result.search_metadata['providers'] == {'gdelt': True, 'google_news': False}


def test_news_fallback_completes_news_coverage_without_masking_primary_failure():
    from app.risk.engine import evaluate
    risk, _ = evaluate(sanctions={'list_size': 10}, litigation={'available': True, 'cases': []},
                       adverse_media=[], identity_confidence=.9, identity_verdict='verified',
                       ownership=[], sources_consulted={'ofac': True, 'gdelt': False,
                       'google_news': True, 'courtlistener': True})
    assert risk['coverage_assessment']['complete'] is True
    assert risk['coverage_assessment']['required_sources'] == ['ofac', 'news', 'courtlistener']
