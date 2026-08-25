"use strict";

/* Shell: shared helpers, hash router, home view.
   The book detail view lives in detail.js and attaches itself to window.LF.
   Every string that comes from the server is injected with textContent only. */

const LF = (window.LF = {});

const HEX_RE = /^#[0-9a-fA-F]{6}$/;
const BOOK_ROUTE = /^#\/book\/([a-z0-9-]{1,64})$/;
const NO_KEY_MESSAGE =
  "Set ANTHROPIC_API_KEY on the server to generate bibles. " +
  "The book is saved — browsing and editing keep working without a key.";
const SNIPPET = 140;

const noticeBar = document.getElementById("notice");
const views = {
  home: document.getElementById("view-home"),
  detail: document.getElementById("view-detail"),
};
const grid = document.getElementById("book-grid");
const emptyNote = document.getElementById("book-empty");
const countBadge = document.getElementById("book-count");
const form = document.getElementById("new-book-form");
const submitBtn = document.getElementById("f-submit");
const formNote = document.getElementById("form-note");

async function request(method, path, payload) {
  const options = { method: method, headers: { Accept: "application/json" } };
  if (payload !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  const res = await fetch(path, options);
  const body = await res.json().catch(() => ({ ok: false, error: "bad response" }));
  if (!res.ok || !body.ok) {
    const err = new Error(body.error || "request failed");
    err.status = res.status;
    throw err;
  }
  return body.data;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function button(label, className, onClick) {
  const node = el("button", className || "btn", label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

/* Data-driven colour: the hex comes from the model, so it is matched against
   #RRGGBB before it may reach the style property. Everything else about the
   swatch (size, border, radius) is styled by the .swatch class in style.css. */
function paintSwatch(node, hex) {
  if (HEX_RE.test(hex || "")) node.style.backgroundColor = hex;
  return node;
}

function swatchStrip(palette) {
  const strip = el("div", "swatch-strip");
  (palette || []).forEach((color) =>
    strip.appendChild(paintSwatch(el("span", "swatch"), color && color.hex))
  );
  return strip;
}

function clearNotice() {
  noticeBar.replaceChildren();
  noticeBar.className = "notice hidden";
}

function showNotice(message, variant, actionLabel, action) {
  noticeBar.replaceChildren();
  noticeBar.className = "notice notice-" + (variant || "info");
  noticeBar.appendChild(el("span", "notice-text", message));
  if (actionLabel) noticeBar.appendChild(button(actionLabel, "btn btn-small", action));
  noticeBar.appendChild(button("Dismiss", "btn btn-small", clearNotice));
}

function snippet(text) {
  const value = (text || "").trim();
  return value.length > SNIPPET ? value.slice(0, SNIPPET) + "…" : value;
}

Object.assign(LF, {
  HEX_RE: HEX_RE,
  NO_KEY_MESSAGE: NO_KEY_MESSAGE,
  request: request,
  el: el,
  button: button,
  paintSwatch: paintSwatch,
  showNotice: showNotice,
  clearNotice: clearNotice,
  generate: (slug) => request("POST", "/api/books/" + slug + "/generate"),
});

// -- home ------------------------------------------------------------------
function askDelete(card, actions, slug) {
  actions.classList.add("hidden");
  const bar = el("div", "confirm-bar");
  const restore = () => {
    bar.remove();
    actions.classList.remove("hidden");
  };
  bar.appendChild(el("span", "confirm-text", "Delete this book?"));
  bar.appendChild(
    button("Delete", "btn btn-small btn-danger", async () => {
      try {
        await request("DELETE", "/api/books/" + slug);
        await loadBooks();
      } catch (err) {
        restore();
        showNotice("Delete failed: " + err.message, "error");
      }
    })
  );
  bar.appendChild(button("Cancel", "btn btn-small", restore));
  card.appendChild(bar);
}

function bookCard(book) {
  const card = el("article", "card");
  card.dataset.slug = book.slug;
  const title = el("h3", "card-title");
  const link = el("a", "link", book.name || "(untitled)");
  link.href = "#/book/" + book.slug;
  title.appendChild(link);
  card.appendChild(title);
  card.appendChild(el("p", "card-text", snippet(book.concept)));
  const meta = el("div", "card-meta");
  meta.appendChild(el("span", "badge", book.status || "empty"));
  if (book.board_count) meta.appendChild(el("span", "badge badge-shot", "🖼 " + book.board_count));
  if (book.recovered) meta.appendChild(el("span", "badge badge-warn", "recovered"));
  card.appendChild(meta);
  if (book.palette && book.palette.length) card.appendChild(swatchStrip(book.palette));
  const actions = el("div", "card-actions");
  actions.appendChild(
    button("Open", "btn btn-small", () => {
      location.hash = "#/book/" + book.slug;
    })
  );
  actions.appendChild(
    button("Delete", "btn btn-small btn-danger", () => askDelete(card, actions, book.slug))
  );
  card.appendChild(actions);
  return card;
}

function renderBooks(books) {
  grid.replaceChildren();
  countBadge.textContent = String(books.length);
  emptyNote.classList.toggle("hidden", books.length > 0);
  books.forEach((book) => grid.appendChild(bookCard(book)));
}

async function loadBooks() {
  try {
    renderBooks(await request("GET", "/api/books"));
  } catch (err) {
    grid.replaceChildren();
    emptyNote.classList.remove("hidden");
    emptyNote.textContent = "Could not load books: " + err.message;
  }
}

function setBusy(busy, label) {
  submitBtn.disabled = busy;
  formNote.textContent = busy ? label : "";
}

/* Generation is a second call after creation: a failed generate leaves the
   saved book in place, so the user can retry without retyping the concept. */
async function generateThenOpen(slug) {
  setBusy(true, "Generating…");
  try {
    await LF.generate(slug);
    clearNotice();
    location.hash = "#/book/" + slug;
  } catch (err) {
    if (err.status === 503) showNotice(NO_KEY_MESSAGE, "warn", "Open book", () => {
      location.hash = "#/book/" + slug;
    });
    else showNotice("Generation failed: " + err.message, "error", "Retry", () => generateThenOpen(slug));
    await loadBooks();
  } finally {
    setBusy(false);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    concept: document.getElementById("f-concept").value,
    style: document.getElementById("f-style").value,
    density: Number(document.getElementById("f-density").value),
    lang: document.getElementById("f-lang").value,
  };
  setBusy(true, "Creating…");
  let created;
  try {
    created = await request("POST", "/api/books", payload);
    form.reset();
  } catch (err) {
    showNotice("Could not create book: " + err.message, "error");
    setBusy(false);
    return;
  }
  await generateThenOpen(created.slug);
});

// -- routing ---------------------------------------------------------------
function showView(name) {
  Object.keys(views).forEach((key) => views[key].classList.toggle("hidden", key !== name));
}

function route() {
  const match = BOOK_ROUTE.exec(location.hash || "#/");
  if (match) {
    showView("detail");
    LF.openDetail(match[1]);
    return;
  }
  showView("home");
  loadBooks();
}

window.addEventListener("hashchange", route);
// fires after detail.js has registered LF.openDetail (both scripts are classic)
window.addEventListener("DOMContentLoaded", route);
