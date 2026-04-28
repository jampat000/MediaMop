from types import SimpleNamespace

from mediamop.modules.subber import subber_subtitle_search_service as svc
from mediamop.modules.subber.subber_opensubtitles_client import SubberRateLimitError
from mediamop.modules.subber.subber_provider_registry import PROVIDER_OPENSUBTITLES_COM, PROVIDER_PODNAPISI


def test_rate_limited_provider_is_skipped_and_next_provider_is_tried(monkeypatch) -> None:
    tried: list[str] = []
    events: list[dict[str, str]] = []
    providers = [
        SimpleNamespace(provider_key=PROVIDER_OPENSUBTITLES_COM),
        SimpleNamespace(provider_key=PROVIDER_PODNAPISI),
    ]
    state_row = SimpleNamespace(id=42, language_code="en", media_scope="movies")
    settings_row = SimpleNamespace(exclude_hearing_impaired=False)

    monkeypatch.setattr(svc, "provider_is_ready_for_search", lambda settings, row: True)
    monkeypatch.setattr(svc, "language_preferences_list", lambda row: ["en"])

    def rate_limited(**kwargs):
        tried.append(kwargs["prow"].provider_key)
        raise SubberRateLimitError("OpenSubtitles daily limit reached")

    def podnapisi_success(**kwargs):
        tried.append(kwargs["prow"].provider_key)
        return True

    monkeypatch.setattr(svc, "_try_opensubtitles_provider", rate_limited)
    monkeypatch.setattr(svc, "_try_podnapisi", podnapisi_success)

    ok = svc.search_and_download_subtitle(
        settings=SimpleNamespace(),
        settings_row=settings_row,
        state_row=state_row,
        db=SimpleNamespace(),
        providers=providers,
        provider_events=events,
    )

    assert ok is True
    assert tried == [PROVIDER_OPENSUBTITLES_COM, PROVIDER_PODNAPISI]
    assert events == [
        {
            "provider": PROVIDER_OPENSUBTITLES_COM,
            "result": "skipped",
            "reason": "rate_limited",
            "message": (
                "opensubtitles_com is rate-limited for this run, so Subber skipped it "
                "and continued with the next enabled provider."
            ),
            "detail": "OpenSubtitles daily limit reached",
        }
    ]
