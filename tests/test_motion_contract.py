"""Offline behavior contracts for motion.js; no browser, server, or packages needed."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "static" / "motion.js"
NODE = shutil.which("node")

# This small DOM implements only selectors/events used by the motion controller.
# Mutation records are delivered explicitly, so icon churn and batched updates
# can be tested without a browser or third-party DOM implementation.
HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');

function fixture(options = {}) {
  const calls = [], observers = [], events = [], writes = [];
  let styleReads = 0;
  class Events {
    constructor() { this.listeners = new Map(); }
    addEventListener(type, callback, opts) {
      const listeners = this.listeners.get(type) || [];
      listeners.push({callback, once: opts && opts.once});
      this.listeners.set(type, listeners);
    }
    removeEventListener(type, callback) {
      this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item.callback !== callback));
    }
    dispatchEvent(event) {
      event.target ||= this;
      for (const item of [...(this.listeners.get(event.type) || [])]) {
        item.callback(event);
        if (item.once) this.removeEventListener(event.type, item.callback);
      }
    }
  }
  class Element extends Events {
    constructor(tag = 'div', attrs = {}) {
      super(); this.nodeType = 1; this.tagName = tag; this.attrs = {...attrs};
      this.children = []; this.parentElement = null; this.css = {};
      this.style = new Proxy({}, {set(_, key) { writes.push(key); throw new Error('Inline style write'); }});
      this.classList = {contains: token => (this.attrs.class || '').split(/\s+/).includes(token)};
      if (options.noAnimate) this.animate = undefined;
    }
    get hidden() { return Object.hasOwn(this.attrs, 'hidden'); }
    set hidden(value) { if (value) this.attrs.hidden = ''; else delete this.attrs.hidden; }
    get open() { return Object.hasOwn(this.attrs, 'open'); }
    set open(value) { if (value) this.attrs.open = ''; else delete this.attrs.open; }
    get isConnected() { return html.contains(this); }
    getAttribute(name) { return this.attrs[name] ?? null; }
    setAttribute() { writes.push('attribute'); throw new Error('Attribute write'); }
    focus() { throw new Error('Motion must not change focus'); }
    contains(node) { return this === node || this.children.some(child => child.contains(node)); }
    append(...nodes) {
      for (const node of nodes) {
        if (node.parentElement) node.parentElement.children = node.parentElement.children.filter(child => child !== node);
        node.parentElement = this; this.children.push(node);
      }
      return nodes[0];
    }
    replace(...nodes) {
      const removed = [...this.children];
      this.children = []; removed.forEach(node => node.parentElement = null);
      this.append(...nodes); return removed;
    }
    matches(selector) {
      return selector.split(',').some(raw => {
        const part = raw.trim();
        if (part.includes('>')) {
          const [parent, child] = part.split('>').map(item => item.trim());
          return this.matches(child) && this.parentElement && this.parentElement.matches(parent);
        }
        if (part.startsWith('#')) return this.attrs.id === part.slice(1);
        if (part.startsWith('.')) return this.classList.contains(part.slice(1));
        if (part.startsWith('[')) {
          const match = part.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
          assert.ok(match, `Unsupported test selector: ${part}`);
          return match[2] === undefined ? Object.hasOwn(this.attrs, match[1]) : this.attrs[match[1]] === match[2];
        }
        return this.tagName === part;
      });
    }
    querySelectorAll(selector) {
      const found = [];
      for (const child of this.children) {
        if (child.matches(selector)) found.push(child);
        found.push(...child.querySelectorAll(selector));
      }
      return found;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    animate(frames, settings) {
      if (options.throwAnimate) throw new Error('WAAPI not usable');
      const animation = {
        cancelled: false, cancelCount: 0,
        cancel() { this.cancelled = true; this.cancelCount++; this.oncancel?.(); },
        finish() { this.onfinish?.(); },
      };
      calls.push({target: this, frames, settings, animation});
      return animation;
    }
  }
  const el = (tag, attrs) => new Element(tag, attrs);
  const html = el('html'), body = html.append(el('body'));
  const workspace = body.append(el('main', {id: 'workspace'}));
  const v1 = workspace.append(el('section', {id: 'view1', class: 'view on'}));
  const v2 = workspace.append(el('section', {id: 'view2', class: 'view'}));
  const mode = v1.append(el('div', {class: 'mode-panel on'}));
  const otherMode = v1.append(el('div', {class: 'mode-panel'}));
  const panel = v2.append(el('section', {'data-evidence-panel': 'articles'}));
  const otherPanel = v2.append(el('section', {'data-evidence-panel': 'report', hidden: ''}));
  const list = panel.append(el('tbody', {id: 'resultsList'}));
  const row = () => el('tr');
  list.append(row());
  const details = panel.append(el('details'));
  const summary = details.append(el('summary'));
  const content = details.append(el('div'));
  const bar = content.append(el('i', {'data-motion-bar': '', style: 'width:73%'}));
  const document = new Events();
  document.hidden = false;
  document.readyState = options.loading ? 'loading' : 'complete';
  document.querySelector = selector => html.querySelector(selector);
  const media = new Events(); media.matches = !!options.reduced;
  if (options.legacyMedia) {
    media.addListener = callback => Events.prototype.addEventListener.call(media, 'change', callback);
    media.removeListener = callback => Events.prototype.removeEventListener.call(media, 'change', callback);
    media.addEventListener = undefined; media.removeEventListener = undefined;
  }
  class MutationObserver {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(root, config) { this.root = root; this.config = config; }
    disconnect() { this.disconnected = true; }
  }
  class CustomEvent {
    constructor(type, init) { this.type = type; this.detail = init?.detail; }
  }
  document.addEventListener('brahma:motion-ready', event => events.push(event));
  const window = {
    matchMedia: () => media,
    MutationObserver: options.noObserver ? undefined : MutationObserver,
    getComputedStyle(node) { styleReads++; return {display: 'block', visibility: 'visible', ...node.css}; },
  };
  if (options.noWorkspace) body.replace();
  vm.runInNewContext(source, {window, document, CustomEvent});
  const api = window.BrahmaMotion;
  const attr = (target, name, value) => {
    const oldValue = target.getAttribute(name);
    if (value === null) delete target.attrs[name]; else target.attrs[name] = value;
    return {type: 'attributes', target, attributeName: name, oldValue};
  };
  const children = (target, addedNodes = [], removedNodes = []) => ({type: 'childList', target, addedNodes, removedNodes});
  const mutate = (...records) => {
    for (const observer of observers) {
      if (!observer.disconnected) observer.callback(records.filter(record => observer.root.contains(record.target)));
    }
  };
  const navigate = () => mutate(attr(v1, 'class', 'view'), attr(v2, 'class', 'view on'));
  const reduce = value => { media.matches = value; media.dispatchEvent({type: 'change', matches: value}); };
  const background = value => { document.hidden = value; document.dispatchEvent({type: 'visibilitychange'}); };
  return {el, workspace, body, v1, v2, mode, otherMode, panel, otherPanel, list, row,
    details, summary, content, bar, calls, writes, observers, events, document, media,
    api, attr, children, mutate, navigate, reduce, background, reads: () => styleReads};
}
"""


@unittest.skipUnless(NODE, "Node is required for offline motion behavior tests")
class MotionContractTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(
            [NODE, "-e", HARNESS + "\n" + body, str(SCRIPT)],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_initial_load_is_still_and_observer_is_scoped(self):
        self.run_js(r"""
const f = fixture();
assert.equal(f.calls.length, 0);
assert.equal(f.events.length, 1);
assert.equal(f.events[0].detail.api, f.api);
assert.equal(f.observers.length, 1);
assert.equal(f.observers[0].root, f.workspace);
assert.equal(f.observers[0].config.subtree, true);
assert.equal(f.observers[0].config.attributeFilter.includes('style'), false);
assert.equal(f.observers[0].config.attributeFilter.includes('hidden'), true);
assert.deepEqual(f.writes, []);
""")

    def test_navigation_tracks_state_not_clicks_and_deduplicates_mutations(self):
        self.run_js(r"""
const f = fixture(); f.navigate();
assert.equal(f.calls.length, 1);
const call = f.calls[0];
assert.equal(call.target, f.v2);
assert.equal(call.settings.duration, 180);
assert.equal(call.settings.easing, 'cubic-bezier(.2,.8,.2,1)');
assert.equal(call.frames[0].opacity, 0);
assert.equal(call.frames[0].transform, 'translateY(6px)');
assert.equal(call.frames[1].opacity, 1);
f.mutate(f.attr(f.v2, 'class', 'view on filters-open'));
f.mutate(f.attr(f.v2, 'class', 'view on filters-open'));
assert.equal(f.calls.length, 1);
f.mutate(f.attr(f.v2, 'class', 'view'), f.attr(f.v1, 'class', 'view on'));
assert.equal(call.animation.cancelled, true);
assert.equal(f.calls.at(-1).target, f.v1);
assert.deepEqual(f.writes, []);
""")

    def test_mode_switch_and_hidden_evidence_report_tabs(self):
        self.run_js(r"""
const f = fixture();
f.mutate(f.attr(f.mode, 'class', 'mode-panel'), f.attr(f.otherMode, 'class', 'mode-panel on'));
assert.equal(f.calls.at(-1).target, f.otherMode);
f.navigate(); const count = f.calls.length;
f.mutate(f.attr(f.panel, 'hidden', ''), f.attr(f.otherPanel, 'hidden', null));
assert.equal(f.calls.length, count + 1);
assert.equal(f.calls.at(-1).target, f.otherPanel);
assert.equal(f.calls.at(-1).settings.duration, 180);
const report = f.el('section', {role: 'tabpanel', 'data-report-panel': 'team', hidden: ''});
f.otherPanel.append(report); f.mutate(f.children(f.otherPanel, [report]));
const before = f.calls.length;
f.mutate(f.attr(report, 'hidden', null));
assert.equal(f.calls.length, before + 1);
assert.equal(f.calls.at(-1).target, report);
""")

    def test_twenty_rendered_rows_finish_within_240ms(self):
        self.run_js(r"""
const f = fixture(); f.navigate(); f.calls.length = 0;
const rows = Array.from({length: 20}, () => f.row());
const removed = f.list.replace(...rows);
f.mutate(f.children(f.list, rows, removed));
assert.equal(f.calls.length, 20);
assert.equal(f.calls[0].settings.delay, 0);
assert.equal(f.calls[1].settings.delay, 18);
assert.equal(f.calls.at(-1).settings.delay, 60);
for (const {target, settings, frames} of f.calls) {
  assert.ok(rows.includes(target));
  assert.ok(settings.duration + settings.delay <= 240);
  assert.equal(settings.fill, 'backwards');
  assert.equal(settings.iterations, undefined);
  assert.equal(frames[0].width, undefined);
}
const stale = [...f.calls];
const newRows = [f.el('article'), f.el('div', {'data-motion-row': ''})];
f.mutate(f.children(f.list, newRows, f.list.replace(...newRows)));
assert.ok(stale.every(call => call.animation.cancelled));
assert.equal(f.calls.length, 22);
f.mutate(f.children(f.list));
assert.equal(f.calls.length, 22);
""")

    def test_icon_replacements_and_unrelated_classes_do_not_restart_motion(self):
        self.run_js(r"""
const f = fixture(); f.navigate();
const icon = f.list.children[0].append(f.el('i', {'data-lucide': 'arrow'}));
const svg = f.el('svg', {class: 'lucide'});
const row = f.list.children[0]; row.replace(svg);
const before = f.calls.length, reads = f.reads();
f.mutate(f.children(row, [svg], [icon]), f.attr(svg, 'class', 'lucide active'));
assert.equal(f.calls.length, before);
assert.equal(f.reads(), reads);
assert.equal(f.calls[0].animation.cancelled, false);
""")

    def test_disclosure_content_and_bar_have_distinct_motion(self):
        self.run_js(r"""
const f = fixture(); f.navigate(); f.calls.length = 0;
f.mutate(f.attr(f.details, 'open', ''));
assert.equal(f.calls.length, 2);
const content = f.calls.find(call => call.target === f.content);
const bar = f.calls.find(call => call.target === f.bar);
assert.equal(content.settings.duration, 140);
assert.equal(bar.frames[0].transform, 'scaleX(0)');
assert.equal(bar.frames[1].transform, 'scaleX(1)');
assert.equal(bar.frames[0].transformOrigin, 'left center');
assert.equal(bar.frames[0].width, undefined);
assert.equal(f.bar.getAttribute('style'), 'width:73%');
assert.ok(f.calls.every(call => call.target !== f.summary && call.target !== f.details));
f.mutate(f.attr(f.details, 'open', null));
assert.ok(f.calls.every(call => call.animation.cancelled));
f.mutate(f.attr(f.details, 'open', ''));
assert.equal(f.calls.length, 4);
""")

    def test_hidden_views_closed_details_and_detached_nodes_never_animate(self):
        self.run_js(r"""
const f = fixture();
f.api.enter(f.content); f.api.enter(f.bar); f.api.enter(f.otherPanel);
const rows = [f.row(), f.row()];
f.mutate(f.children(f.list, rows, f.list.replace(...rows)));
assert.equal(f.calls.length, 0);
f.navigate();
assert.ok(f.calls.every(call => call.target !== f.content && call.target !== f.bar));
const outside = f.body.append(f.el('section', {'data-motion-panel': ''}));
f.api.enter(outside); f.api.enter(f.el('div'));
assert.equal(f.calls.length, 1);
f.otherPanel.hidden = false; f.otherPanel.css.display = 'none';
f.api.enter(f.otherPanel);
assert.equal(f.calls.length, 1);
""")

    def test_reduced_motion_cancels_immediately_and_does_not_replay(self):
        self.run_js(r"""
const f = fixture({reduced: true}); f.navigate();
f.mutate(f.attr(f.details, 'open', '')); f.api.enter(f.v2);
assert.equal(f.calls.length, 0);
f.reduce(false); assert.equal(f.calls.length, 0);
f.api.enter(f.content); assert.ok(f.calls.length > 0);
const started = [...f.calls]; f.reduce(true);
assert.ok(started.every(call => call.animation.cancelled));
f.api.enter(f.v2); assert.equal(f.calls.length, started.length);
f.reduce(false); assert.equal(f.calls.length, started.length);
""")

    def test_document_visibility_cancels_and_never_replays_background_changes(self):
        self.run_js(r"""
const f = fixture(); f.navigate(); const initial = f.calls[0];
f.background(true); assert.equal(initial.animation.cancelled, true);
f.mutate(f.attr(f.details, 'open', ''));
const rows = [f.row()]; f.mutate(f.children(f.list, rows, f.list.replace(...rows)));
f.api.enter(f.v2); assert.equal(f.calls.length, 1);
f.background(false); f.api.refresh(); assert.equal(f.calls.length, 1);
f.api.enter(f.content); assert.ok(f.calls.length > 1);
""")

    def test_explicit_enter_replaces_animation_and_stale_completion_is_safe(self):
        self.run_js(r"""
const f = fixture(); f.api.enter(f.mode);
const first = f.calls.at(-1).animation;
f.api.enter(f.mode); const second = f.calls.at(-1).animation;
assert.equal(first.cancelled, true); first.finish();
f.api.cancel(f.mode); assert.equal(second.cancelled, true);
f.api.enter(f.mode); const third = f.calls.at(-1).animation; third.finish();
f.api.cancel(); assert.equal(third.cancelled, false);
assert.deepEqual(f.writes, []);
""")

    def test_api_event_fallback_works_without_mutation_observer(self):
        self.run_js(r"""
const f = fixture({noObserver: true});
f.attr(f.v1, 'class', 'view'); f.attr(f.v2, 'class', 'view on');
f.document.dispatchEvent({type: 'brahma:rendered', detail: {root: f.v2}});
assert.equal(f.calls.length, 1); assert.equal(f.calls[0].target, f.v2);
f.document.dispatchEvent({type: 'brahma:rendered', detail: {root: f.v2}});
assert.equal(f.calls.length, 1);
f.api.enter(f.v2); assert.equal(f.calls.length, 2);
""")

    def test_missing_or_throwing_waapi_is_fail_open(self):
        self.run_js(r"""
for (const options of [{noAnimate: true}, {throwAnimate: true}]) {
  const f = fixture(options); f.navigate();
  f.mutate(f.attr(f.details, 'open', '')); f.api.enter(f.v2); f.api.cancel();
  assert.equal(f.calls.length, 0);
  assert.equal(f.v2.classList.contains('on'), true);
  assert.equal(f.panel.hidden, false);
  assert.equal(f.details.open, true);
  assert.deepEqual(f.writes, []);
}
""")

    def test_event_and_observer_for_one_render_do_not_double_animate(self):
        self.run_js(r"""
const f = fixture(); f.navigate(); f.calls.length = 0;
const rows = [f.row(), f.row()]; const removed = f.list.replace(...rows);
f.document.dispatchEvent({type: 'brahma:rendered', detail: {root: f.list}});
assert.equal(f.calls.length, 2);
f.mutate(f.children(f.list, rows, removed));
assert.equal(f.calls.length, 2);
assert.ok(f.calls.every(call => !call.animation.cancelled));
""")

    def test_parent_entry_cancels_child_motion_and_destroy_cancels_detached_rows(self):
        self.run_js(r"""
const f = fixture(); f.navigate(); f.api.enter(f.panel);
const child = f.calls.at(-1).animation;
f.api.enter(f.v2);
assert.equal(child.cancelled, true);
const rows = [f.row(), f.row()];
f.mutate(f.children(f.list, rows, f.list.replace(...rows)));
const rowCalls = f.calls.filter(call => rows.includes(call.target));
assert.equal(rowCalls.length, 2);
// Teardown can happen before the browser delivers the removal records.
f.list.replace(); f.api.destroy();
assert.ok(rowCalls.every(call => call.animation.cancelled));
""")

    def test_styles_and_aria_hidden_are_respected_without_replaying_existing_panels(self):
        self.run_js(r"""
const f = fixture(); f.navigate(); f.calls.length = 0;
const panel = f.panel.append(f.el('section', {'data-motion-panel': ''}));
panel.css.visibility = 'hidden';
f.mutate(f.children(f.panel, [panel]));
assert.equal(f.calls.length, 0);
panel.css.visibility = 'visible';
f.document.dispatchEvent({type: 'brahma:rendered', detail: {root: panel}});
assert.equal(f.calls.length, 1);
assert.equal(f.calls[0].target, panel);
f.mutate(f.attr(panel, 'aria-hidden', 'true'));
assert.equal(f.calls[0].animation.cancelled, true);
f.mutate(f.attr(panel, 'aria-hidden', 'false'));
assert.equal(f.calls.length, 2);
assert.equal(f.calls[1].target, panel);
""")

    def test_deferred_startup_legacy_media_and_cleanup(self):
        self.run_js(r"""
const f = fixture({loading: true, legacyMedia: true});
assert.equal(f.observers.length, 0);
f.document.dispatchEvent({type: 'DOMContentLoaded'});
assert.equal(f.events.length, 1);
f.navigate(); f.reduce(true);
assert.equal(f.calls[0].animation.cancelled, true);
f.reduce(false); f.api.enter(f.v2);
const last = f.calls.at(-1).animation;
f.api.destroy(); assert.equal(last.cancelled, true);
assert.equal(f.observers[0].disconnected, true);
assert.equal(f.media.listeners.get('change').length, 0);
assert.equal(f.document.listeners.get('visibilitychange').length, 0);
const count = f.calls.length; f.api.enter(f.v1); f.api.refresh(); f.reduce(false);
assert.equal(f.calls.length, count);
const early = fixture({loading: true}); early.api.destroy();
early.document.dispatchEvent({type: 'DOMContentLoaded'});
assert.equal(early.observers.length, 0);
const missing = fixture({noWorkspace: true});
missing.api.enter(); missing.api.refresh(); missing.api.cancel(); missing.api.destroy();
assert.equal(missing.calls.length, 0);
""")


if __name__ == "__main__":
    unittest.main()
