"""Keyboard and visibility contracts for the developer workspace tabs."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_developer_tabs_keep_focus_and_visible_panel_in_sync():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for frontend behavior checks")
    source = (Path(__file__).resolve().parents[1] / "static/app.js").read_text()
    navigation = source.split("function setDeveloperTab(key){", 1)[1].split("const CONTRACT=", 1)[0]
    harness = r'''
const assert = require('node:assert/strict');
const keys = ['setup', 'playground', 'contract'];
let focused = null;
const tabs = keys.map(key => ({
  dataset: {developerTab: key}, tabIndex: key === 'setup' ? 0 : -1,
  attrs: {'aria-selected': String(key === 'setup')},
  setAttribute(name, value) { this.attrs[name] = value; },
  focus() { focused = this; },
}));
const panels = keys.map(key => ({dataset: {developerPanel: key}, hidden: key !== 'setup'}));
const document = {querySelectorAll: selector => selector === '[data-developer-tab]' ? tabs : panels};
const list = {querySelectorAll: () => tabs};
function check(key) {
  assert.deepEqual(panels.filter(panel => !panel.hidden).map(panel => panel.dataset.developerPanel), [key]);
  assert.deepEqual(tabs.filter(tab => tab.tabIndex === 0).map(tab => tab.dataset.developerTab), [key]);
  assert.deepEqual(tabs.filter(tab => tab.attrs['aria-selected'] === 'true').map(tab => tab.dataset.developerTab), [key]);
}
function press(index, key) {
  let prevented = false;
  developerTabKey({currentTarget: list, target: tabs[index], key,
    preventDefault() { prevented = true; }});
  return prevented;
}
setDeveloperTab('playground'); check('playground');
assert.equal(press(1, 'ArrowRight'), true); check('contract'); assert.equal(focused, tabs[2]);
press(2, 'ArrowRight'); check('setup'); assert.equal(focused, tabs[0]);
press(0, 'ArrowLeft'); check('contract');
press(2, 'Home'); check('setup');
press(0, 'End'); check('contract');
setDeveloperTab('unknown'); check('contract');
assert.equal(press(2, 'Enter'), false); check('contract');
assert.equal(press(-1, 'ArrowLeft'), false); check('contract');
'''
    result = subprocess.run([node, "-e", "function setDeveloperTab(key){" + navigation + harness],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
