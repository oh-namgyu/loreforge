"use strict";

const grid = document.getElementById("book-grid");
const emptyNote = document.getElementById("book-empty");
const countBadge = document.getElementById("book-count");

async function apiGet(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await res.json().catch(() => ({ ok: false, error: "bad response" }));
  if (!res.ok || !body.ok) throw new Error(body.error || "request failed");
  return body.data;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function bookCard(book) {
  const card = el("article", "card");
  card.appendChild(el("h3", "card-title", book.name || book.slug));
  card.appendChild(el("p", "card-text", book.concept || ""));
  card.appendChild(el("span", "badge", book.status || "empty"));
  if (book.recovered) card.appendChild(el("span", "badge badge-warn", "recovered"));
  return card;
}

function render(books) {
  grid.replaceChildren();
  countBadge.textContent = String(books.length);
  emptyNote.classList.toggle("hidden", books.length > 0);
  books.forEach((book) => grid.appendChild(bookCard(book)));
}

async function load() {
  try {
    render(await apiGet("/api/books"));
  } catch (err) {
    grid.replaceChildren();
    emptyNote.classList.remove("hidden");
    emptyNote.textContent = "Could not load books: " + err.message;
  }
}

load();
