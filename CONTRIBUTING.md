# Contributing to loreforge

Thanks for your interest! loreforge is a small, dependency-light project and
contributions are welcome.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium         # once, for the browser tests

python -m pytest -q                 # unit suite (no network, no API key)
python -m pytest e2e -q             # browser round trips against a real server

LOREFORGE_FAKE_LLM=1 python app.py  # run the UI offline at http://127.0.0.1:6180
```

`LOREFORGE_FAKE_LLM=1` swaps both providers for offline fakes, so you can develop
the whole app without keys or spending anything. The e2e suite skips itself
rather than failing when chromium is not installed.

## Conventions

- **Keep files small.** A source file over ~300 lines, or a function over ~50,
  wants splitting.
- **No inline styles.** Every style is a reusable class in the global
  `static/style.css` — no `style="..."` attributes, no per-component stylesheets.
- **`textContent` only** for user- and model-derived strings. `innerHTML` with
  such data is a stored-XSS bug, and the tests check for it.
- **Keep dependencies minimal.** Flask plus the two provider SDKs, which are
  imported lazily so the tests never need them.
- **Providers stay behind the seam.** New image backends implement the
  `ImageProvider` protocol in `core/providers/base.py`.
- **Type hints** on new functions.
- **Add or update tests** in `tests/` (or `e2e/`) for every behaviour change.

## Pull requests

Keep PRs focused on one change. Describe what changed and how you verified it,
and make sure `python -m pytest -q` is green before opening one. CI runs the unit
suite on Python 3.10 and 3.12, the e2e suite on 3.12, and a Docker build smoke
test.
