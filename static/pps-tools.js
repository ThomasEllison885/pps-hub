/**
 * PPS Hub — satellite tool launcher (Proposal Generator, PPM, TPS).
 * Uses same-tab navigation on phones/tablets so Safari does not block pop-ups.
 */
(function () {
  'use strict';

  function ppsPreferSameTab() {
    if (typeof window.matchMedia === 'function') {
      if (window.matchMedia('(max-width: 768px)').matches) return true;
      if (window.matchMedia('(pointer: coarse)').matches) return true;
    }
    return navigator.maxTouchPoints > 0 && window.innerWidth < 1024;
  }

  function ppsOpenUrl(url) {
    if (ppsPreferSameTab()) {
      window.location.assign(url);
    } else {
      window.open(url, '_blank', 'noopener');
    }
  }

  async function openTool(baseUrl, loadId, errorMessage) {
    const failMsg = errorMessage || 'Could not open tool. Please try again from the dashboard.';
    try {
      const resp = await fetch('/generate-code', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!resp.ok) {
        const err = await resp.json().catch(function () { return {}; });
        throw new Error(err.error || 'SSO failed');
      }
      const data = await resp.json();
      const code = data.code || data.token;
      if (!code) throw new Error('No code');
      let url = baseUrl + '?code=' + encodeURIComponent(code);
      if (loadId != null && loadId !== '') {
        url += '&load=' + encodeURIComponent(loadId);
      }
      ppsOpenUrl(url);
    } catch (e) {
      console.log('openTool error:', e);
      alert(failMsg);
    }
  }

  window.ppsPreferSameTab = ppsPreferSameTab;
  window.ppsOpenUrl = ppsOpenUrl;
  window.openTool = openTool;
})();