/* Optional, state-driven enhancement. Content and navigation never depend on motion.
 * Load after app.js. Existing .view/.mode-panel, tab panels, #resultsList and
 * details work automatically inside #workspace (or [data-motion-workspace]).
 * Optional hooks: data-motion-panel, data-motion-row, data-motion-bar.
 * Bars keep their final width in markup/CSS; only their horizontal scale moves.
 * API: BrahmaMotion.enter(root), refresh(), cancel(root), destroy().
 * Emit brahma:rendered with detail: {root} to refresh after non-observed updates.
 * brahma:motion-ready is emitted on document with detail: {api} after setup.
 */
(() => {
  "use strict";

  const PANEL = '.view, .mode-panel, [role="tabpanel"], [data-report-panel], [data-evidence-panel], [data-motion-panel], #evidenceFilters';
  const ROW = '#resultsList > tr, #resultsList > article, [data-motion-row]';
  const BAR = '[data-motion-bar]';
  const HOOK = `${PANEL}, ${ROW}, ${BAR}, details, #resultsList`;
  const EASING = 'cubic-bezier(.2,.8,.2,1)';
  const animations = new WeakMap();
  const visibility = new WeakMap();
  const disclosures = new WeakMap();
  const active = new Set();
  const media = typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  let workspace = null;
  let observer = null;
  let destroyed = false;

  const element = node => node && node.nodeType === 1;
  const within = node => element(node) && workspace && workspace.contains(node);
  const allowed = () => !destroyed && !document.hidden && !(media && media.matches);

  function visible(target) {
    if (!within(target) || !target.isConnected) return false;
    for (let node = target; node; node = node.parentElement) {
      if (node.hidden || node.getAttribute('aria-hidden') === 'true') return false;
      if (node.matches('.view, .mode-panel') && !node.classList.contains('on')) return false;
      if (node !== target && node.matches('details') && !node.open) {
        const summary = Array.from(node.children).find(child => child.matches('summary'));
        if (!summary || !summary.contains(target)) return false;
      }
      const style = window.getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse') return false;
    }
    return true;
  }

  function cancelTarget(target) {
    const animation = animations.get(target);
    animations.delete(target);
    active.delete(target);
    if (animation) animation.cancel();
  }

  function cancel(root = null) {
    for (const target of active) {
      if (!root || root === target || root.contains(target)) cancelTarget(target);
    }
  }

  function play(target, kind, duration, delay = 0) {
    cancelTarget(target);
    if (!allowed() || !visible(target) || typeof target.animate !== 'function') return;
    const frames = kind === 'bar'
      ? [{transform: 'scaleX(0)', transformOrigin: 'left center'},
         {transform: 'scaleX(1)', transformOrigin: 'left center'}]
      : [{opacity: 0, transform: 'translateY(6px)'},
         {opacity: 1, transform: 'translateY(0)'}];
    let animation;
    try {
      // No inline styles or persistent fill: failures/cancellation reveal real data.
      animation = target.animate(frames, {duration, delay, easing: EASING, fill: 'backwards'});
    } catch {
      return;
    }
    animations.set(target, animation);
    active.add(target);
    const release = () => {
      if (animations.get(target) === animation) {
        animations.delete(target);
        active.delete(target);
      }
    };
    animation.onfinish = release;
    animation.oncancel = release;
  }

  function collect() {
    const entries = new Map();
    const add = (selector, kind) => {
      workspace.querySelectorAll(selector).forEach(target => entries.set(target, {kind, duration: 180}));
    };
    add(PANEL, 'panel');
    add(ROW, 'row');
    add(BAR, 'bar');
    workspace.querySelectorAll('details').forEach(details => {
      const open = details.open && visible(details);
      const opening = open && disclosures.get(details) !== true;
      disclosures.set(details, open);
      Array.from(details.children).forEach(child => {
        if (child.matches('summary')) return;
        if (!entries.has(child)) entries.set(child, {kind: 'disclosure', duration: 140});
        // Opening a disclosure takes precedence over a direct child's panel entry.
        if (opening && entries.get(child).kind !== 'bar') entries.get(child).duration = 140;
      });
    });
    return entries;
  }

  function scan(animate = true, forceRoot = null) {
    if (!workspace || destroyed) return;
    for (const target of active) {
      if (!allowed() || !visible(target)) cancelTarget(target);
    }
    const entries = collect();
    if (forceRoot && forceRoot !== workspace && !forceRoot.matches('details, #resultsList') && !entries.has(forceRoot)) {
      entries.set(forceRoot, {kind: 'panel', duration: 180});
    }
    const entering = new Map();
    entries.forEach((entry, target) => {
      const shown = visible(target);
      const wasShown = visibility.get(target);
      visibility.set(target, shown);
      if (shown && (wasShown !== true || (forceRoot && forceRoot.contains(target)))) entering.set(target, entry);
    });
    if (!animate || !allowed()) return;

    let rowIndex = 0;
    entering.forEach((entry, target) => {
      // A panel carries its children with it; avoid stacked fades/translations.
      if (entry.kind !== 'bar') {
        for (let parent = target.parentElement; parent && parent !== workspace; parent = parent.parentElement) {
          if (entering.has(parent)) {
            cancelTarget(target);
            return;
          }
        }
      }
      const delay = entry.kind === 'row' ? Math.min(rowIndex++ * 18, 60) : 0;
      play(target, entry.kind, entry.duration, delay);
    });
  }

  function relevant(record) {
    const target = record.target;
    if (!element(target)) return false;
    if (record.type === 'attributes') {
      if (record.attributeName === 'open') return target.matches('details');
      if (record.attributeName !== 'class') return true;
      if (target.matches('.view, .mode-panel')) {
        const old = new Set((record.oldValue || '').split(/\s+/));
        return ['on', 'filters-open'].some(token => old.has(token) !== target.classList.contains(token));
      }
      return target === workspace || target.matches(PANEL);
    }
    if (target.matches('#resultsList, details')) return true;
    return [...record.addedNodes, ...record.removedNodes].some(node => {
      if (!element(node)) return false;
      if (node.matches(HOOK) || node.querySelector(HOOK)) return true;
      return Array.from(active).some(target => node.contains(target));
    });
  }

  function refresh() {
    scan();
  }

  function enter(root = workspace) {
    if (within(root)) scan(true, root);
  }

  function rendered(event) {
    const root = event.detail && event.detail.root;
    if (within(root || event.target)) refresh();
  }

  function preferenceChanged() {
    if (!allowed()) cancel();
    // Consume changes while suspended; never replay missed motion on return.
    scan(false);
  }

  function destroy() {
    destroyed = true;
    if (observer) observer.disconnect();
    cancel();
    document.removeEventListener('DOMContentLoaded', init);
    document.removeEventListener('visibilitychange', preferenceChanged);
    document.removeEventListener('brahma:rendered', rendered);
    if (media && typeof media.removeEventListener === 'function') media.removeEventListener('change', preferenceChanged);
    else if (media && typeof media.removeListener === 'function') media.removeListener(preferenceChanged);
    observer = null;
    workspace = null;
  }

  const api = {enter, refresh, cancel, destroy};
  window.BrahmaMotion = api;

  function init() {
    if (destroyed || workspace) return;
    workspace = document.querySelector('#workspace, [data-motion-workspace]');
    if (!workspace) return;
    scan(false); // Initial content is immediately readable, with no load choreography.
    if (typeof window.MutationObserver === 'function') {
      observer = new window.MutationObserver(records => {
        if (records.some(relevant)) refresh();
      });
      observer.observe(workspace, {subtree: true, childList: true, attributes: true,
        attributeFilter: ['class', 'hidden', 'open', 'aria-hidden'], attributeOldValue: true});
    }
    document.addEventListener('brahma:rendered', rendered);
    document.addEventListener('visibilitychange', preferenceChanged);
    if (media && typeof media.addEventListener === 'function') media.addEventListener('change', preferenceChanged);
    else if (media && typeof media.addListener === 'function') media.addListener(preferenceChanged);
    document.dispatchEvent(new CustomEvent('brahma:motion-ready', {detail: {api}}));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
