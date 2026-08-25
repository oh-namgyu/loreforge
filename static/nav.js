"use strict";

/* Scroll spy for the detail side nav.

   Given [{panel, link}] pairs, the topmost panel still inside the reading band
   owns the highlight. One observer at a time: a new call disconnects the old
   one, so re-rendering the detail view never leaves stale panels observed.
   Browsers without IntersectionObserver simply get no highlight — the nav
   buttons still scroll, because that is plain click handling in detail.js. */

(function (LF) {
  const BAND = "-16% 0px -60% 0px";
  const ACTIVE = "is-active";

  let watcher = null;

  LF.sectionSpy = function (pairs) {
    if (watcher) {
      watcher.disconnect();
      watcher = null;
    }
    if (!pairs.length || typeof IntersectionObserver !== "function") return;
    const onScreen = new Set();
    watcher = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) onScreen.add(entry.target);
          else onScreen.delete(entry.target);
        });
        const lead = pairs.find((pair) => onScreen.has(pair.panel)) || pairs[0];
        pairs.forEach((pair) => pair.link.classList.toggle(ACTIVE, pair === lead));
      },
      { rootMargin: BAND }
    );
    pairs.forEach((pair) => watcher.observe(pair.panel));
  };
})(window.LF);
