"use strict";

/* Board rendering and export: the actionbar controls and the gallery section.
   Images come from /api/books/<slug>/image/<kind>; the rendered_at stamp rides
   along as a cache buster so a re-render replaces the picture in place.
   Failures are kept here so the section can repaint them after a re-render. */

(function (LF) {
  const el = LF.el;
  const button = LF.button;
  const RENDER_LABEL = "Render Board";
  const NO_IMAGE_MESSAGE =
    "Set OPENAI_API_KEY on the server to render images. " +
    "Generating, editing and export keep working without it.";

  const renderBtn = document.getElementById("detail-render");
  const exportBtn = document.getElementById("detail-export");
  const boardBox = document.getElementById("kind-board");
  const soloBox = document.getElementById("kind-solo");

  let failures = [];
  let shownFor = null;

  function selectedKinds() {
    const kinds = [];
    if (boardBox.checked) kinds.push("board");
    if (soloBox.checked) kinds.push("solo");
    return kinds;
  }

  function imageUrl(slug, entry) {
    return (
      "/api/books/" + slug + "/image/" + entry.kind +
      "?t=" + encodeURIComponent(entry.rendered_at || "")
    );
  }

  function shot(slug, entry) {
    const figure = el("figure", "shot");
    figure.dataset.kind = entry.kind;
    const img = el("img", "shot-img");
    img.src = imageUrl(slug, entry);
    img.alt = entry.kind + " render";
    figure.appendChild(img);
    figure.appendChild(el("figcaption", "shot-cap", entry.kind + " · " + (entry.rendered_at || "")));
    return figure;
  }

  function failureChip(item) {
    const chip = el("span", "chip chip-error");
    chip.dataset.kind = item.kind;
    chip.appendChild(el("span", "chip-text", item.kind + ": " + item.error));
    chip.appendChild(button("Retry", "btn btn-small", () => run([item.kind])));
    return chip;
  }

  async function run(kinds) {
    if (!kinds.length) {
      LF.showNotice("Pick at least one image kind.", "warn");
      return;
    }
    renderBtn.disabled = true;
    renderBtn.textContent = "Rendering…";
    try {
      const path = "/api/books/" + LF.detail.slug() + "/render";
      const data = await LF.request("POST", path, { kinds: kinds });
      failures = data.failed || [];
      LF.detail.show(data.book);
      if (failures.length) LF.showNotice("Some images failed — see the Board section.", "warn");
      else LF.clearNotice();
    } catch (err) {
      if (err.status === 409 && err.message === "no-image-provider") {
        LF.showNotice(NO_IMAGE_MESSAGE, "warn");
      } else {
        LF.showNotice("Render failed: " + err.message, "error");
      }
    } finally {
      renderBtn.disabled = false;
      renderBtn.textContent = RENDER_LABEL;
    }
  }

  /* Called by detail.js before the sections are rebuilt: a different book
     starts with a clean slate, and the button follows whether a bible exists. */
  LF.gallerySync = function (book) {
    const slug = LF.detail.slug();
    if (slug !== shownFor) {
      failures = [];
      shownFor = slug;
    }
    const ready = Boolean(book && book.bible);
    renderBtn.disabled = !ready;
    exportBtn.disabled = !ready;
  };

  LF.gallerySection = function () {
    const slug = LF.detail.slug();
    const book = LF.detail.book() || {};
    const board = Array.isArray(book.board) ? book.board : [];
    const box = el("div", "stack");
    const chips = el("div", "chip-row");
    chips.id = "render-errors";
    failures.forEach((item) => chips.appendChild(failureChip(item)));
    box.appendChild(chips);
    const gallery = el("div", "gallery");
    gallery.id = "gallery";
    if (!board.length) {
      gallery.appendChild(el("p", "empty", "No renders yet — use Render Board above."));
    }
    board.forEach((entry) => gallery.appendChild(shot(slug, entry)));
    box.appendChild(gallery);
    return box;
  };

  renderBtn.addEventListener("click", () => run(selectedKinds()));

  // the endpoint answers with Content-Disposition: attachment, so the new tab
  // hands the file straight to the browser's downloader
  exportBtn.addEventListener("click", () => {
    window.open("/api/books/" + LF.detail.slug() + "/export", "_blank", "noopener");
  });
})(window.LF);
