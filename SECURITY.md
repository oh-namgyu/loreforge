# Security Policy

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.x (latest on `main`) | :white_check_mark: |
| older commits          | :x:                |

loreforge is pre-1.0. Only the latest state of the default branch receives fixes.

## Reporting a vulnerability

Please report security issues **privately** through
[GitHub Security Advisories](https://github.com/oh-namgyu/loreforge/security/advisories/new)
on this repository. Do not open a public issue for a sensitive report. You can
expect an initial response within a few days.

## Threat model

loreforge is a **single-user, self-hosted** tool. It binds `127.0.0.1` by
default, holds no user accounts, and treats the machine it runs on as trusted.
The interesting boundaries are the network exposure of the HTTP port and the
untrusted text that comes back from an LLM.

## Built-in hardening

- **Bind guard.** Binding a non-loopback address without `AUTH_TOKEN` is a hard
  startup failure (`SystemExit(1)`), not a warning. Misconfigured exposure is
  therefore impossible to do silently.
- **Token authentication.** With `AUTH_TOKEN` set, a login form takes the token,
  compares it with `hmac.compare_digest` (constant time), and issues a session
  cookie whose value is `HMAC-SHA256(AUTH_TOKEN, timestamp)`. The cookie is
  `httpOnly`, `SameSite=Strict`, `Secure` when the request is HTTPS, and expires
  after 8 hours. Without a token the app is in open mode — intended only for a
  loopback bind.
- **Same-origin gate.** `POST` / `PATCH` / `PUT` / `DELETE` additionally require an
  `Origin` or `Referer` whose host:port matches the request host. Combined with
  `SameSite=Strict` this covers CSRF and DNS rebinding.
- **Content-Security-Policy.** Every response carries
  `default-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'`,
  plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`.
- **Slug guard.** Book slugs must match `^[a-z0-9-]{1,64}$`, and the resolved path
  is re-checked to be a direct child of `data/books/` before any read or write.
  Path traversal is rejected with `400`.
- **Stored-XSS defence.** Model- and user-derived strings are injected into the UI
  with `textContent` only — `innerHTML` is not used for such data. The export
  document escapes every string server-side with `html.escape`. Palette values
  are used as CSS only after matching `^#[0-9a-fA-F]{6}$`.
- **Secret handling.** API keys are read from the server environment only. They
  are never persisted, echoed in a response, or logged.
- **No upload, no outbound fetch.** The app accepts no file uploads and fetches no
  user-supplied URLs. Its only outbound traffic is to the two configured LLM
  providers.
- **Atomic writes.** `book.json` is written to a temp file and `os.replace`d, with
  the previous good copy rotated to `book.json.bak`; deletes are an atomic
  `os.rename` into `data/.trash/`.

## Plaintext transport — read before exposing

**loreforge does not terminate TLS.** Traffic, including the token you type into
the login form, is plain HTTP. A non-loopback bind prints a warning saying so.

If you expose it beyond loopback, putting it behind a **TLS-terminating reverse
proxy** (nginx, Caddy, Traefik) is a requirement, not a suggestion. The
`SameSite=Strict` cookie is also only marked `Secure` when the request arrives
over HTTPS, which requires that proxy.

## Known limitations

- **No rate limiting.** Nothing throttles login attempts, generation or rendering.
  A leaked token is both an access problem and a spending problem. Rate limit at
  the reverse proxy if the instance is reachable by anyone else.
- **One shared token.** There are no accounts and no per-user separation; everyone
  who has `AUTH_TOKEN` has full access to every book.
- **Single process.** Storage safety relies on in-process locks, so running
  multiple workers is unsupported and unsafe.
- **Trusted local machine.** `data/` is stored unencrypted, readable by anything
  running as the same user.
