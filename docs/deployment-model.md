# Supported deployment model

MediaMop 1.x is designed for a simple, explicit runtime:

- one application process
- one host or one container instance
- one SQLite database writer topology
- same-origin web app and API by default

Horizontal scaling, multiple app processes, and multiple uvicorn workers are not supported unless a future release moves job coordination and rate limiting to shared external storage.

## Workers

Module worker settings such as Refiner and Pruner worker counts control in-process job slots inside the single application process. They do not make MediaMop multi-node safe.

Docker and Windows packaged runtimes start one uvicorn process. Do not add `--workers` to the Docker command or run multiple MediaMop containers against the same SQLite database.

## Rate limiting

Login and bootstrap rate limiting is process-local memory. This is correct only because the supported runtime is single-process. If multiple app processes are started, each process has its own rate-limit buckets and protection becomes misleading.

## Reverse proxies

MediaMop ignores `X-Forwarded-For` unless `MEDIAMOP_TRUSTED_PROXY_IPS` is configured. Set it to the immediate reverse proxy IP or CIDR only, for example:

```text
MEDIAMOP_TRUSTED_PROXY_IPS=172.18.0.1,10.0.0.0/24
```

When the immediate peer is trusted, MediaMop uses the right-most untrusted address in `X-Forwarded-For` as the client key. Forwarded headers from untrusted peers are ignored.

For an HTTPS reverse proxy, terminate TLS at the proxy, keep the MediaMop hop on
the private network, and set the proxy's address in `MEDIAMOP_TRUSTED_PROXY_IPS`.
The proxy should send exactly one `X-Forwarded-Proto: https` value. MediaMop
only accepts that protocol value from the configured immediate peer; a browser
cannot spoof it directly. For example, an nginx deployment can use:

```nginx
location / {
    proxy_pass http://127.0.0.1:8788;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

Set `MEDIAMOP_SESSION_COOKIE_SECURE=true` and, only when every browser reaches
the proxy over HTTPS, `MEDIAMOP_SECURITY_ENABLE_HSTS=1`. Plain HTTP localhost
development may explicitly set `MEDIAMOP_SESSION_COOKIE_SECURE=false`; the
Security settings screen reports this trade-off.

## CORS

Credentialed browser requests require explicit origins. `MEDIAMOP_CORS_ORIGINS=*` is rejected at startup.
