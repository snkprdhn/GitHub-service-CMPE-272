# CMPE 272 HW 2 GitHub Service

This project is our implementation of Homework 2 for CMPE 272. It is a small FastAPI service that wraps the GitHub Issues REST API for one configured repository. The service can create, list, read, update, close, and reopen issues, add comments, and receive signed GitHub webhooks.

## Team

- Sonit: FastAPI setup, configuration, models, health endpoint, request IDs, and error responses
- Sagar: GitHub REST client, issue and comment routes, pagination, rate-limit handling, and ETag support
- Joel: Webhook signature verification, event validation, deduplication, event storage, and webhook routes
- Mathew: Unit and integration tests, OpenAPI contract, Docker setup, CI workflow, and documentation


## Project files

```text
app/                 FastAPI application and GitHub integration
tests/               Unit tests, integration tests, and fixtures
openapi.yaml         OpenAPI 3.1 contract
DESIGN.md            Short design note
RUNBOOK.md           Full demo and screenshot instructions
Dockerfile           Container build
Makefile             Run, lint, test, and coverage commands
```

## Requirements

- Python 3.12 or newer
- A GitHub repository used for issue testing
- A fine-grained GitHub personal access token with **Only select repositories** set to the test repository
- GitHub repository permission: **Issues: Read and write**; no additional write scopes are needed by the service
- Docker for the container run
- ngrok

## Local setup

From the project directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

Fill in `.env` with the test repository information:

```dotenv
GITHUB_TOKEN=github_pat_REPLACE_WITH_YOUR_TOKEN
GITHUB_OWNER=REPLACE_WITH_THE_REPOSITORY_OWNER
GITHUB_REPO=REPLACE_WITH_THE_TEST_REPOSITORY_NAME
WEBHOOK_SECRET=REPLACE_WITH_A_RANDOM_SECRET
PORT=8000
SERVICE_BASE_URL=http://localhost:8000
```

A webhook secret can be generated locally with:

```sh
openssl rand -hex 32
```

## Running locally without Docker

```sh
make run
```

The default addresses are:

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/healthz>

`make run` reads `PORT` from `.env`.

## API routes

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/issues` | Create an issue |
| `GET` | `/issues` | List issues with state, label, and pagination filters |
| `GET` | `/issues/{number}` | Get one issue |
| `PATCH` | `/issues/{number}` | Edit, close, or reopen an issue |
| `POST` | `/issues/{number}/comments` | Add a comment |
| `POST` | `/webhook` | Receive a signed GitHub webhook |
| `GET` | `/events` | View recent accepted webhook deliveries |
| `GET` | `/healthz` | Check whether the service is running |

The complete request and response definitions are in `openapi.yaml`.

## API examples

These examples use HTTPie, which is installed by `requirements-dev.txt`. Together they cover every service route.

Check service health:

```sh
.venv/bin/http GET :8000/healthz
```

Create an issue:

```sh
.venv/bin/http POST :8000/issues \
  title="CMPE 272 API test" \
  body="Issue created through the local service."
```

List open issues:

```sh
.venv/bin/http GET :8000/issues state==open page==1 per_page==30
```

To see the forwarded GitHub pagination header, create more than one issue and use `per_page=1`:

```sh
.venv/bin/http --headers GET :8000/issues state==all page==1 per_page==1
```

Get one issue:

```sh
.venv/bin/http GET :8000/issues/1
```

Update and close an issue:

```sh
.venv/bin/http PATCH :8000/issues/1 \
  title="Updated CMPE 272 API test" \
  body="Updated through the service." \
  state=closed
```

Reopen the issue:

```sh
.venv/bin/http PATCH :8000/issues/1 state=open
```

Add a comment:

```sh
.venv/bin/http POST :8000/issues/1/comments \
  body="Comment created through the service."
```

View stored webhook events:

```sh
.venv/bin/http GET :8000/events limit==20
```

Replace issue number `1` with the number returned by `POST /issues`.

Send a locally signed request to the webhook route:

```sh
body='{"zen":"Manual webhook test"}'
signature=$(
  .venv/bin/python -c 'import hashlib,hmac,sys; from app.config import get_settings; body=sys.argv[1].encode(); secret=get_settings().webhook_secret.encode(); print("sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest())' "$body"
)

.venv/bin/http POST :8000/webhook \
  Content-Type:application/json \
  X-GitHub-Event:ping \
  X-GitHub-Delivery:manual-delivery-1 \
  X-Hub-Signature-256:"$signature" \
  --raw "$body"
```

The expected response is `204 No Content`. Calling `GET /events` afterward shows the stored `ping` delivery.

## Webhook setup

Start the service, then expose port 8000 in a second terminal:

```sh
ngrok http 8000
```

In the GitHub test repository, open **Settings**, then **Webhooks**, and add a webhook with these values:

- Payload URL: `https://YOUR-NGROK-HOST/webhook`
- Content type: `application/json`
- Secret: the same value as `WEBHOOK_SECRET` in `.env`
- Events: **Issues** and **Issue comments**
- Active: enabled

GitHub first sends a `ping` event. Creating an issue or comment then sends a real delivery. A valid delivery returns `204 No Content` and appears in `GET /events`.

To test a retry, open the webhook's **Recent Deliveries** page, select a delivery, and choose **Redeliver**. The service uses the delivery ID and action as its deduplication key, so the repeated event is acknowledged but not stored twice.

## Tests

Run lint and the offline tests:

```sh
make lint
.venv/bin/python -m pytest -m "not integration" -q
make coverage
```

The unit tests cover request validation, GitHub error mapping, pagination parsing, ETag reuse, webhook signatures, tampered payloads, supported events, and duplicate deliveries.

Run the live GitHub issue lifecycle test after configuring `.env`:

```sh
.venv/bin/python -m pytest -m integration -k issue_lifecycle -v
```

Run the real webhook integration test while the service, tunnel, and GitHub webhook are active:

```sh
.venv/bin/python -m pytest -m integration -k real_webhook -v
```

## Running locally with Docker

Build the image:

```sh
docker build -t github-issues-service .
```

Run it with the same `.env` configuration:

```sh
docker run --rm --env-file .env -p 8000:8000 github-issues-service
```

Check the container from another terminal:

```sh
.venv/bin/http GET :8000/healthz
```

## GitHub Actions

The workflow in `.github/workflows/ci.yml` runs for pushes and pull requests. It checks Ruff formatting, runs the offline tests, and builds the Docker image.

## Implementation notes

- GitHub credentials and repository settings come from environment variables.
- Requests to GitHub use `application/vnd.github+json` and the current GitHub API version header.
- GitHub `Link` pagination headers are forwarded to API clients.
- GitHub rate-limit responses are returned as `429` with `Retry-After` when available.
- Repeated issue-list requests cache GitHub ETags and send `If-None-Match`.
- Webhook signatures are calculated from the raw request body with HMAC-SHA256 and compared in constant time.
- Logs include request IDs and GitHub delivery IDs without logging secrets or raw signatures..
