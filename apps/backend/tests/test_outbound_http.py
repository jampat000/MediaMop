from __future__ import annotations

import ssl

from mediamop.platform.outbound_http import _secure_external_tls_context


def test_external_tls_context_requires_tls_1_2_or_newer() -> None:
    context = _secure_external_tls_context()

    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
