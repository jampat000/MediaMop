---
sidebar_position: 1
title: API Reference
---

# API Reference

Weir exposes a REST API via FastAPI. The API is served at `/api/v1` under the same origin as the web UI.

## OpenAPI specification

The full OpenAPI schema is auto-generated from the FastAPI backend and available at:

- **Development**: `http://localhost:8788/docs` (Swagger UI) or `http://localhost:8788/redoc` (ReDoc)
- **Source**: [`apps/web/openapi/weir-openapi.json`](https://github.com/jampat000/Weir/blob/main/apps/web/openapi/weir-openapi.json)

## Authentication

Weir uses cookie-based sessions with CSRF protection:

- First-run bootstrap creates the admin user
- Login via `POST /api/v1/auth/login`
- Session cookies are HTTP-only and secure (when behind HTTPS)
- State-changing requests require CSRF tokens

## Key endpoints

### Health and readiness

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Process liveness check |
| `/ready` | GET | No | Full readiness (DB, migrations) |
| `/metrics` | GET | Token | Prometheus metrics |

### Refiner

| Prefix | Description |
|--------|-------------|
| `/api/v1/refiner/` | Libraries, files, rule sets, jobs, and maintenance |
| `/api/v1/pause` | The one pause switch for processing |

### Platform

| Prefix | Description |
|--------|-------------|
| `/api/v1/auth/` | Authentication and session management |
| `/api/v1/activity/` | Activity log and history |
| `/api/v1/settings/` | Application settings |
| `/api/v1/suite/` | Suite-level settings, updates, diagnostics |
| `/api/v1/browse/` | Local filesystem browser |

## TypeScript types

The frontend generates TypeScript types from the OpenAPI schema:

```bash
cd apps/web
npm run api:types:sync
```

This produces typed API clients in `apps/web/src/lib/api/generated/openapi-types.ts`.
