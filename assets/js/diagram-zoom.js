/* Site-wide click-to-zoom lightbox for mermaid diagrams.
   Loaded by layouts/_partials/extend-footer.html on pages that use the
   mermaid shortcode; styles live in assets/css/custom.css (.diagram-zoom).
   Click a diagram to open it full-screen: wheel or pinch zooms, drag pans,
   the +/− buttons step zoom, ×/Escape/backdrop close, double-click refits. */
(function () {
  'use strict';

  var MIN_SCALE = 0.2;
  var MAX_SCALE = 12;
  var BTN_STEP = 1.3;
  var WHEEL_STEP = 1.15;
  var FIT_PAD = 56; // px of breathing room around the fitted diagram

  function svgSize(svg) {
    var vb = svg.viewBox && svg.viewBox.baseVal;
    if (vb && vb.width && vb.height) return { w: vb.width, h: vb.height };
    var r = svg.getBoundingClientRect();
    return { w: r.width || 800, h: r.height || 600 };
  }

  function openZoom(diagram) {
    var source = diagram.querySelector('svg');
    if (!source) return;
    var size = svgSize(source);

    var overlay = document.createElement('div');
    overlay.className = 'diagram-zoom';
    overlay.innerHTML =
      '<div class="diagram-zoom__panel">' +
      '<div class="diagram-zoom__stage"></div>' +
      '<div class="diagram-zoom__controls">' +
      '<button class="diagram-zoom__btn" data-zoom="in" aria-label="Zoom in" title="Zoom in">+</button>' +
      '<button class="diagram-zoom__btn" data-zoom="out" aria-label="Zoom out" title="Zoom out">&minus;</button>' +
      '<button class="diagram-zoom__btn" data-zoom="close" aria-label="Close" title="Close">&times;</button>' +
      '</div></div>';
    var panel = overlay.firstChild;
    var stage = panel.querySelector('.diagram-zoom__stage');

    // Clone at natural (viewBox) size; mermaid's inline max-width/width
    // styles would otherwise fight the transform math.
    var svg = source.cloneNode(true);
    svg.removeAttribute('style');
    svg.setAttribute('width', size.w);
    svg.setAttribute('height', size.h);
    stage.appendChild(svg);

    document.body.appendChild(overlay);
    document.documentElement.classList.add('diagram-zoom-open');

    var scale = 1;
    var tx = 0;
    var ty = 0;

    function apply() {
      stage.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
    }

    // Fit within the panel with FIT_PAD margins; never upscale small
    // diagrams past natural size — whitespace beats blur.
    function fit() {
      var pw = panel.clientWidth;
      var ph = panel.clientHeight;
      scale = Math.min((pw - 2 * FIT_PAD) / size.w, (ph - 2 * FIT_PAD) / size.h, 1);
      scale = Math.max(scale, MIN_SCALE);
      tx = (pw - size.w * scale) / 2;
      ty = (ph - size.h * scale) / 2;
      apply();
    }

    // Zoom keeping the panel-relative point (px, py) fixed on screen.
    // Stage has transform-origin 0 0, so: tx' = px − (px − tx)·f.
    function zoomAt(px, py, factor) {
      var next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * factor));
      factor = next / scale;
      if (factor === 1) return;
      tx = px - (px - tx) * factor;
      ty = py - (py - ty) * factor;
      scale = next;
      apply();
    }

    function onKey(e) {
      if (e.key === 'Escape') close();
    }

    function close() {
      overlay.remove();
      document.documentElement.classList.remove('diagram-zoom-open');
      document.removeEventListener('keydown', onKey);
    }

    panel.addEventListener('wheel', function (e) {
      e.preventDefault();
      var rect = panel.getBoundingClientRect();
      // ctrlKey wheel is a macOS trackpad pinch — track it continuously.
      var factor = e.ctrlKey
        ? Math.exp(-e.deltaY * 0.01)
        : (e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP);
      zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
    }, { passive: false });

    // One pointer pans, two pinch-zoom around their midpoint.
    var pointers = new Map();
    panel.addEventListener('pointerdown', function (e) {
      if (e.target.closest('.diagram-zoom__controls')) return;
      e.preventDefault();
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      // Best-effort: keeps the drag when the pointer leaves the panel.
      try { panel.setPointerCapture(e.pointerId); } catch (err) {}
    });
    panel.addEventListener('pointermove', function (e) {
      var prev = pointers.get(e.pointerId);
      if (!prev) return;
      if (pointers.size === 1) {
        tx += e.clientX - prev.x;
        ty += e.clientY - prev.y;
        apply();
      } else if (pointers.size === 2) {
        var rect = panel.getBoundingClientRect();
        var entries = Array.from(pointers.entries());
        var other = entries[0][0] === e.pointerId ? entries[1][1] : entries[0][1];
        var prevMidX = (prev.x + other.x) / 2 - rect.left;
        var prevMidY = (prev.y + other.y) / 2 - rect.top;
        var prevDist = Math.hypot(prev.x - other.x, prev.y - other.y);
        var midX = (e.clientX + other.x) / 2 - rect.left;
        var midY = (e.clientY + other.y) / 2 - rect.top;
        var dist = Math.hypot(e.clientX - other.x, e.clientY - other.y);
        if (prevDist > 0) zoomAt(prevMidX, prevMidY, dist / prevDist);
        tx += midX - prevMidX;
        ty += midY - prevMidY;
        apply();
      }
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    });
    function releasePointer(e) {
      pointers.delete(e.pointerId);
    }
    panel.addEventListener('pointerup', releasePointer);
    panel.addEventListener('pointercancel', releasePointer);

    panel.addEventListener('dblclick', function (e) {
      if (!e.target.closest('.diagram-zoom__controls')) fit();
    });
    panel.querySelector('[data-zoom="in"]').addEventListener('click', function () {
      zoomAt(panel.clientWidth / 2, panel.clientHeight / 2, BTN_STEP);
    });
    panel.querySelector('[data-zoom="out"]').addEventListener('click', function () {
      zoomAt(panel.clientWidth / 2, panel.clientHeight / 2, 1 / BTN_STEP);
    });
    panel.querySelector('[data-zoom="close"]').addEventListener('click', close);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
    document.addEventListener('keydown', onKey);

    fit();
  }

  function init() {
    document.querySelectorAll('.mermaid').forEach(function (d) {
      if (d.dataset.zoomBound) return;
      d.dataset.zoomBound = '1';
      d.setAttribute('title', 'Click to zoom');
      d.addEventListener('click', function () {
        openZoom(d);
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
