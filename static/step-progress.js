// Mobile-only sticky "Step X of N" indicator for long multi-section forms.
// Usage: include this script and add markup with id="stepProgress" (see .pps-step-progress in pps-global.css).
// Pass a CSS selector for the step sections via data-step-selector on the #stepProgress element.
(function () {
  function init() {
    const bar = document.getElementById('stepProgress');
    if (!bar) return;
    const selector = bar.dataset.stepSelector;
    if (!selector) return;
    const textEl = document.getElementById('stepProgressText');
    const fillEl = document.getElementById('stepProgressFill');

    function update() {
      const sections = document.querySelectorAll(selector);
      const total = sections.length;
      if (!total) { bar.style.display = 'none'; return; }
      const threshold = 140; // header + progress bar height, generous
      let current = 1;
      sections.forEach((sec, i) => {
        if (sec.getBoundingClientRect().top <= threshold) current = i + 1;
      });
      if (textEl) textEl.textContent = `Step ${current} of ${total}`;
      if (fillEl) fillEl.style.width = (current / total * 100) + '%';
    }

    let scheduled = false;
    window.addEventListener('scroll', () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { update(); scheduled = false; });
    }, { passive: true });

    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
