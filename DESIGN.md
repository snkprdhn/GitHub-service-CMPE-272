# Design note

## GitHub errors and pagination

The service translates GitHub authentication and not-found responses directly to 401, 403, and 404. A GitHub `403` with `X-RateLimit-Remaining: 0` becomes `429`; `Retry-After` is forwarded or calculated from `X-RateLimit-Reset`. GitHub 5xx and connection failures become `503` rather than exposing upstream internals. The list endpoint forwards and parses GitHub's `Link` header. It also caches GitHub's ETag by query and sends `If-None-Match` on a repeated list request.

## Webhook safety

The receiver signs the exact raw request bytes with HMAC SHA-256 and compares signatures with `hmac.compare_digest`. It accepts only `ping`, `issues`, and `issue_comment`. The delivery ID and action form the idempotency key, so a repeated delivery is acknowledged without being stored twice. The store is deliberately in-memory to minimize this assignment's code; SQLite would be the appropriate replacement when delivery history must survive restarts.

## Security trade-offs

Secrets are environment variables and `.env` is ignored by Git. Tokens and raw webhook signatures are never returned or logged. The server holds the GitHub fine-grained PAT; callers do not send it. Structured request logs include the request ID, while webhook logs include both request and delivery IDs. All error responses use a small stable schema and include a request ID header for troubleshooting.
