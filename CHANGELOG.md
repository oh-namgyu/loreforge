# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- The Docker image is built on `python:3.14-slim` (was `3.12-slim`).
- Minimum dependency versions raised: `flask>=3.1.3`, `anthropic>=1.13.0`,
  `openai>=3.29.0`; for development, `pytest>=9.1.1` and
  `pytest-playwright>=0.10.0`.

## [0.1.0] - 2026-08-25

Initial public release.

### Added

- A self-hosted Flask app that turns a one-line character concept into a
  structured "bible": profile, background, personality and speech, signature
  lines, a colour palette, world notes and an English master image prompt.
  Generation is one Anthropic call, retried once if the reply fails schema
  validation; body language `en` or `ko`.
- Optional image rendering of the master prompt into a `board` and a `solo`
  image through a pluggable `ImageProvider` (OpenAI `gpt-image-1` by
  default), only when `OPENAI_API_KEY` is set and only on request.
- Web UI: a palette-forward home grid, a book detail page with a sticky
  section nav and inline editing, and a gallery. Edits are validated against
  the generation schema before anything is written.
- Export of a book as one standalone HTML file with images inlined as data
  URIs and no external references.
- Plain-file storage under `data/books/<slug>/`, with deleted books moved to a
  trash folder and purged after 7 days.
- Security defaults: loopback bind, a hard startup failure for a
  non-loopback bind without `AUTH_TOKEN`, token login with an HMAC-signed
  session cookie, an `Origin`/`Referer` gate on writes, and `textContent`-only
  rendering of user- and model-derived strings.
- `LOREFORGE_FAKE_LLM=1` swaps both providers for offline fakes.
- Dockerfile and `compose.yml`.
