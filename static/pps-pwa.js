/**
 * PPS Hub PWA — install prompt (dashboard only).
 * No service worker in Phase 1 — website behavior unchanged.
 */
(function () {
  'use strict';

  var DISMISS_KEY = 'pps_pwa_install_dismissed';
  var DISMISS_DAYS = 14;

  function wasDismissed() {
    try {
      var raw = localStorage.getItem(DISMISS_KEY);
      if (!raw) return false;
      var ts = parseInt(raw, 10);
      if (!ts) return false;
      return Date.now() - ts < DISMISS_DAYS * 86400000;
    } catch (e) {
      return false;
    }
  }

  function dismiss() {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch (e) {}
    var el = document.getElementById('ppsInstallBanner');
    if (el) el.remove();
  }

  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent);
  }

  function isStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches
      || window.navigator.standalone === true;
  }

  function showIOSHint() {
    if (!isIOS() || isStandalone() || wasDismissed()) return;
    var banner = document.createElement('div');
    banner.id = 'ppsInstallBanner';
    banner.className = 'pps-install-banner';
    banner.innerHTML =
      '<div class="pps-install-inner">' +
        '<div class="pps-install-text">' +
          '<strong>Add PPS Hub to your home screen</strong>' +
          '<span>Tap Share → Add to Home Screen for quick field access.</span>' +
        '</div>' +
        '<button type="button" class="pps-install-dismiss" aria-label="Dismiss">✕</button>' +
      '</div>';
    document.body.appendChild(banner);
    banner.querySelector('.pps-install-dismiss').addEventListener('click', dismiss);
  }

  var deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', function (e) {
    if (wasDismissed() || isStandalone()) return;
    e.preventDefault();
    deferredPrompt = e;
    var existing = document.getElementById('ppsInstallBanner');
    if (existing) return;

    var banner = document.createElement('div');
    banner.id = 'ppsInstallBanner';
    banner.className = 'pps-install-banner';
    banner.innerHTML =
      '<div class="pps-install-inner">' +
        '<div class="pps-install-text">' +
          '<strong>Install PPS Hub</strong>' +
          '<span>Add to your home screen for one-tap access in the field.</span>' +
        '</div>' +
        '<button type="button" class="pps-install-action">Install</button>' +
        '<button type="button" class="pps-install-dismiss" aria-label="Dismiss">✕</button>' +
      '</div>';
    document.body.appendChild(banner);

    banner.querySelector('.pps-install-action').addEventListener('click', function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
        dismiss();
      });
    });
    banner.querySelector('.pps-install-dismiss').addEventListener('click', dismiss);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', showIOSHint);
  } else {
    showIOSHint();
  }
})();