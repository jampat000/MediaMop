---
sidebar_position: 3
title: Reverse Proxy
---

# Reverse Proxy Configuration

MediaMop is designed for a single-process, single-instance deployment. Production deployments should expose one canonical HTTPS origin.

## Trusted proxies

MediaMop ignores `X-Forwarded-For` unless `MEDIAMOP_TRUSTED_PROXY_IPS` is configured:

```
MEDIAMOP_TRUSTED_PROXY_IPS=172.18.0.1,10.0.0.0/24
```

When the immediate peer is trusted, MediaMop uses the right-most untrusted address in `X-Forwarded-For` as the client key. Forwarded headers from untrusted peers are ignored.

## CORS

Credentialed browser requests require explicit origins. Setting `MEDIAMOP_CORS_ORIGINS=*` is rejected at startup.

For split-origin deployments (static site and API on different origins):

- Use HTTPS everywhere
- Set `MEDIAMOP_CORS_ORIGINS` to the real web origin
- Set `MEDIAMOP_TRUSTED_BROWSER_ORIGINS` if stricter POST checks are needed
- Session cookies need `SameSite=None; Secure` for credentialed cross-origin fetch

## Rate limiting

Login and bootstrap rate limiting is process-local memory. This is correct only because the supported runtime is single-process. Multiple app processes would each have their own rate-limit buckets.
