"""Offline contracts for the vanilla-JS entry page (unittest or pytest).

These deliberately do not snapshot layout, copy, function bodies, or CSS.
Only literal ID lookups are covered; computed IDs and render timing belong
in browser QA. IDs declared in JS-generated HTML are not startup DOM contracts.
Link checks cover markup, not data-flow or runtime URL sanitization.
"""

from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from urllib.parse import unquote, urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
ORIGIN = "https://frontend-contract.invalid/"
ID_LOOKUP = re.compile(
    r"(?:\bdocument\s*\.\s*getElementById|(?<![\w$])\$)"
    r"\s*\(\s*(['\"])([\w:-]+)\1\s*\)"
)


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.assets = []
        self.links = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "script" and attrs.get("src"):
            self.assets.append(attrs["src"])
        if tag == "link" and "stylesheet" in (attrs.get("rel") or "").lower().split():
            self.assets.append(attrs.get("href") or "")
        if tag == "a":
            self.links.append(attrs)


def literal_ids(script):
    return {match[1] for match in ID_LOOKUP.findall(script)}


def script_markup(script):
    # Parse individual tags, so '<' operators or literal sample code outside
    # markup cannot make HTMLParser consume subsequent generated elements.
    # This is intentionally a bounded markup scan, not a JavaScript parser.
    tags = re.findall(r"<[A-Za-z][^<>]*>", script)
    return Markup("\n".join(tags))


def required_ids(script):
    return literal_ids(script) - set(script_markup(script).ids)


def local_asset(url):
    """Resolve URLs as served from '/', not relative to index.html on disk."""
    parsed = urlsplit(urljoin(ORIGIN, url))
    if parsed.scheme in {"http", "https"} and parsed.netloc != urlsplit(ORIGIN).netloc:
        return None
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported asset scheme: {url}")
    path = unquote(parsed.path)
    if not path.startswith("/static/"):
        raise ValueError(f"Asset is outside the /static mount: {url}")
    target = (STATIC / path.removeprefix("/static/")).resolve()
    if not target.is_relative_to(STATIC.resolve()):
        raise ValueError(f"Asset escapes the static directory: {url}")
    return target


def unsafe_links(markup):
    problems = []
    for attrs in markup.links:
        href = attrs.get("href") or ""
        if attrs.get("target", "").lower() == "_blank":
            rel = set((attrs.get("rel") or "").lower().split())
            if not rel.intersection({"noopener", "noreferrer"}):
                problems.append(f"new-tab link lacks opener isolation: {href}")
        # Template interpolations need a behavioral sanitizer/browser check;
        # HTML escaping alone does not establish a safe navigation scheme.
        if "${" not in href:
            normalized = re.sub(r"[\x00-\x20]", "", href)
            if urlsplit(normalized).scheme.lower() not in {"", "http", "https", "mailto", "tel"}:
                problems.append(f"unsafe literal navigation scheme: {href}")
    return problems


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Markup((STATIC / "index.html").read_text(encoding="utf-8-sig"))
        cls.script = (STATIC / "app.js").read_text(encoding="utf-8-sig")

    def test_literal_javascript_dom_ids_exist_in_entry_html(self):
        required = required_ids(self.script)
        self.assertTrue(required, "No literal ID contracts discovered; review the scanner")
        missing = required - set(self.html.ids)
        self.assertFalse(missing, f"Missing static DOM IDs: {sorted(missing)}")

    def test_entry_html_ids_are_unique(self):
        duplicates = {key: count for key, count in Counter(self.html.ids).items() if count > 1}
        self.assertFalse(duplicates, f"Ambiguous DOM IDs: {duplicates}")

    def test_local_script_and_stylesheet_assets_exist(self):
        self.assertTrue(self.html.assets, "Entry HTML has no script or stylesheet assets")
        for url in self.html.assets:
            with self.subTest(url=url):
                self.assertTrue(url, "Asset URL must not be empty")
                path = local_asset(url)
                if path is not None:
                    self.assertTrue(path.is_file(), f"Asset URL {url!r} resolves to missing {path}")

    def test_contract_script_is_actually_loaded(self):
        paths = {local_asset(url) for url in self.html.assets if url}
        self.assertIn((STATIC / "app.js").resolve(), paths)

    def test_html_and_generated_links_have_safe_static_attributes(self):
        for origin, markup in (("index.html", self.html), ("app.js", script_markup(self.script))):
            with self.subTest(origin=origin):
                self.assertFalse(unsafe_links(markup), unsafe_links(markup))


class ContractScannerTests(unittest.TestCase):
    def test_both_literal_lookup_forms_and_quote_styles(self):
        script = "document . getElementById ( 'name' ); $(\"status\"); $('part'+i); $(variable);"
        self.assertEqual(literal_ids(script), {"name", "status"})

    def test_generated_ids_are_excluded_without_a_hardcoded_allowlist(self):
        script = "$('root'); $('detail'); el.innerHTML = `<div id=\"detail\"></div>`;"
        self.assertEqual(required_ids(script), {"root"})

    def test_missing_primary_id_is_not_exempted(self):
        self.assertEqual(required_ids("$('missing');") - set(Markup('<div id="root"></div>').ids), {"missing"})

    def test_asset_resolution_ignores_query_and_fragment(self):
        self.assertEqual(local_asset('/static/app.js?v=2#boot'), (STATIC / 'app.js').resolve())
        self.assertEqual(local_asset('static/app.js'), (STATIC / 'app.js').resolve())
        self.assertIsNone(local_asset('https://cdn.example.org/app.js'))
        self.assertIsNone(local_asset('//cdn.example.org/app.js'))

    def test_asset_outside_mount_or_encoded_traversal_is_rejected(self):
        for url in ('/app.js', '/static/%2e%2e/app/main.py', 'data:text/javascript,alert(1)'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_asset(url)

    def test_link_checker_rejects_unsafe_literals_and_missing_rel(self):
        bad = Markup('<a href="java&#x09;script:alert(1)">x</a><a href="https://example.org" target="_blank">y</a>')
        self.assertEqual(len(unsafe_links(bad)), 2)
        good = Markup('<a href="https://example.org" target="_blank" rel="external noopener">x</a>')
        self.assertEqual(unsafe_links(good), [])


class SourceLinkRenderingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is optional; static contracts still run")
    def test_article_renderer_only_links_http_sources_and_escapes_headlines(self):
        # Execute the actual renderer, without a browser, app server or network.
        # Stop startup at its first DOM access; all declarations have been read.
        harness = r"""
const fs = require('fs'), vm = require('vm');
const stop = new Error('stop startup'), nodes = new Map();
const context = vm.createContext({URL, window: {addEventListener() {}},
  document: {getElementById() {throw stop;}}});
try { vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context); }
catch (error) {if (error !== stop) throw error;}
context.document.getElementById = id => {
  if (!nodes.has(id)) nodes.set(id, {value: 'severity', innerHTML: '', textContent: ''});
  return nodes.get(id);
};
const urls = ['https://example.org/evidence?a=1&b=2', 'http://example.org/article',
  'javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\tscript:alert(1)',
  'data:text/html,<script>alert(1)</script>', 'file:///etc/passwd', null];
const rendered = [];
for (const url of urls) {
  context.article = {title: '<img src=x onerror=alert(1)>', url, severity: .7,
    source: 'QA fixture', date: '2026-01-01', categories: [], risk_terms: []};
  vm.runInContext('DATA={adverse_media:[article]};renderResults()', context);
  rendered.push({url, html: nodes.get('resultsList').innerHTML});
}
process.stdout.write(JSON.stringify(rendered));
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness, str(STATIC / "app.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=15, check=True,
        )
        for row in json.loads(result.stdout):
            with self.subTest(url=row["url"]):
                markup = Markup(row["html"])
                expected_link = bool(row["url"] and row["url"].startswith(("https://", "http://")))
                self.assertEqual(len(markup.links), int(expected_link))
                self.assertEqual(unsafe_links(markup), [])
                if expected_link:
                    self.assertEqual(markup.links[0]["href"], row["url"])
                self.assertNotIn("<img", row["html"])
                self.assertIn("&lt;img", row["html"])


if __name__ == "__main__":
    unittest.main()
