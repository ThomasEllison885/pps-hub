/**
 * PPS Estimating — takeoff reliability UI (banner, field badges, generate guard).
 */
(function (global) {
  const ICON = {
    high: '✓',
    medium: '◐',
    low: '~',
    manual: '✎',
    missing: '⚠',
  };

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _el(ref) {
    if (!ref) return null;
    return typeof ref === 'string' ? document.getElementById(ref) : ref;
  }

  function renderBanner(confidence, containerRef) {
    const el = _el(containerRef);
    if (!el || !confidence) {
      if (el) el.innerHTML = '';
      return;
    }
    const rl = confidence.report_label ? ` — ${escapeHtml(confidence.report_label)}` : '';
    el.innerHTML = `
      <div class="pps-confidence pps-confidence-${confidence.css || 'medium'}">
        <div class="pps-confidence-title">${escapeHtml(confidence.title || '')}${rl}</div>
        <div class="pps-confidence-headline">${escapeHtml(confidence.headline || '')}</div>
        <div class="pps-confidence-detail">${escapeHtml(confidence.summary_line || '')}</div>
        <div class="pps-confidence-hint">${escapeHtml(confidence.detail || '')}</div>
      </div>`;
  }

  function renderFieldGrid(confidence, containerRef) {
    const el = _el(containerRef);
    if (!el || !confidence || !confidence.fields) {
      if (el) el.innerHTML = '';
      return;
    }
    const rows = confidence.fields.map((f) => {
      const rel = f.reliability || 'missing';
      const icon = ICON[rel] || '·';
      return `
        <div class="pps-reliability-row">
          <span class="pps-reliability-label">${escapeHtml(f.label)}</span>
          <span class="pps-reliability-value">${escapeHtml(f.display != null ? f.display : '—')}</span>
          <span class="pps-reliability-badge pps-rel-${rel}" title="${escapeHtml(f.note || '')}">
            ${icon} ${escapeHtml(f.source_label || rel)}
          </span>
        </div>`;
    }).join('');
    el.innerHTML = `<div class="pps-reliability-grid">${rows}</div>`;
  }

  function renderWarnings(warnings, containerRef) {
    const el = _el(containerRef);
    if (!el) return;
    const items = (warnings || []).map(
      (w) => `<div class="parsed-warn">⚠ ${escapeHtml(w)}</div>`
    ).join('');
    el.innerHTML = items;
  }

  function renderParsedBlock(confidence, warnings, opts) {
    opts = opts || {};
    if (opts.bannerId) renderBanner(confidence, opts.bannerId);
    if (opts.gridId) renderFieldGrid(confidence, opts.gridId);
    if (opts.warnId) renderWarnings(warnings, opts.warnId);
    if (opts.boxId || opts.box) {
      const box = _el(opts.box || opts.boxId);
      if (box) box.style.display = confidence ? 'block' : 'none';
    }
  }

  function confirmGenerate(confidence) {
    if (!confidence || !confidence.overall || confidence.overall === 'high') {
      return true;
    }
    const msg = confidence.confirm_message || 'Review takeoff confidence before continuing. Proceed?';
    return global.confirm(msg);
  }

  async function fetchConfidence(tool, payload) {
    const r = await fetch('/estimating/confidence', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool, ...payload }),
      credentials: 'same-origin',
    });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || 'Confidence check failed');
    return d.confidence;
  }

  global.PPSReliability = {
    renderBanner,
    renderFieldGrid,
    renderParsedBlock,
    confirmGenerate,
    fetchConfidence,
  };
})(window);