"""Contract suite fixtures: a running Weir server, HTTP clients, and fakes for the outside world.

Nothing here imports Weir. See ``tests/contract/README.md``.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.contract.support import launcher  # noqa: E402
from tests.contract.support.client import WeirClient  # noqa: E402
from tests.contract.support.fake_ffmpeg import FakeFfmpeg, real_ffmpeg_dir  # noqa: E402
from tests.contract.support.fake_manager import FakeManager  # noqa: E402

CONTRACT_DIR = Path(__file__).resolve().parent
AREAS: list[dict[str, Any]] = json.loads((CONTRACT_DIR / "areas.json").read_text(encoding="utf-8"))["areas"]
AREA_NAMES = [a["name"] for a in AREAS]


# --- options, markers, area selection ---------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("weir-contract")
    group.addoption(
        "--contract-area",
        action="append",
        default=[],
        metavar="AREA[,AREA]",
        help=f"Run only these contract areas ({', '.join(AREA_NAMES)}). Repeatable or comma-separated.",
    )
    group.addoption(
        "--contract-required-only",
        action="store_true",
        default=False,
        help="Run only the areas areas.json marks required for the backend under test (WEIR_CONTRACT_SERVER).",
    )


def pytest_configure(config: pytest.Config) -> None:
    for area in AREAS:
        config.addinivalue_line("markers", f"{area['name']}: contract area - {area['description']}")
    config.addinivalue_line(
        "markers", "real_ffmpeg: uses the real ffmpeg/ffprobe on tiny generated files; skipped when they are missing"
    )
    config.addinivalue_line(
        "markers",
        "backends(*kinds, reason): runs only against these servers (python, dotnet); skipped with the reason on others",
    )
    config.addinivalue_line(
        "markers",
        "known_bug(issue, backends=(...)): the test asserts CORRECT behaviour for a filed GitHub issue "
        "that a listed backend still gets wrong; xfail(strict=True) there so a fix flips it to a failing "
        "XPASS, which is the prompt to delete the marker. Omit backends to mean every server kind.",
    )


def _area_of(item: pytest.Item) -> str | None:
    try:
        relative = Path(str(item.fspath)).resolve().relative_to(CONTRACT_DIR)
    except ValueError:
        return None
    return relative.parts[0] if len(relative.parts) > 1 else None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    wanted: set[str] = set()
    for raw in config.getoption("--contract-area") or []:
        wanted.update(part.strip() for part in raw.split(",") if part.strip())
    unknown = wanted.difference(AREA_NAMES)
    if unknown:
        raise pytest.UsageError(
            f"Unknown contract area(s): {', '.join(sorted(unknown))}. Known: {', '.join(AREA_NAMES)}"
        )
    kind = launcher.server_kind()
    if config.getoption("--contract-required-only"):
        required = {a["name"] for a in AREAS if kind in a.get("required", [])}
        wanted = wanted & required if wanted else required

    dotnet_reason = launcher.dotnet_unavailable_reason() if kind == "dotnet" else None
    ffmpeg_missing = real_ffmpeg_dir() is None
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        area = _area_of(item)
        if area is None:
            continue
        if area not in AREA_NAMES:
            raise pytest.UsageError(
                f"{item.nodeid} is in tests/contract/{area}/, which is not an area in areas.json. "
                "Add the area there or move the test."
            )
        item.add_marker(getattr(pytest.mark, area))
        if wanted and area not in wanted:
            deselected.append(item)
            continue
        if dotnet_reason is not None:
            item.add_marker(pytest.mark.skip(reason=dotnet_reason))
        backends = item.get_closest_marker("backends")
        if backends is not None:
            unknown_kinds = set(backends.args).difference(launcher.SERVER_KINDS)
            if not backends.args or unknown_kinds:
                raise pytest.UsageError(
                    f"{item.nodeid}: @pytest.mark.backends needs server kinds from {', '.join(launcher.SERVER_KINDS)}; "
                    f"got {backends.args!r}"
                )
            if kind not in backends.args:
                reason = backends.kwargs.get("reason") or f"runs only against {', '.join(backends.args)}"
                item.add_marker(pytest.mark.skip(reason=reason))
        if ffmpeg_missing and item.get_closest_marker("real_ffmpeg") is not None:
            item.add_marker(
                pytest.mark.skip(reason="ffmpeg and ffprobe are not on PATH (or WEIR_CONTRACT_REAL_FFMPEG_DIR)")
            )
        for known_bug in item.iter_markers(name="known_bug"):
            issue = known_bug.kwargs.get("issue")
            if issue is None and known_bug.args:
                issue = known_bug.args[0]
            if issue is None:
                raise pytest.UsageError(f"{item.nodeid}: @pytest.mark.known_bug needs issue=<GitHub issue number>")
            bug_backends = known_bug.kwargs.get("backends") or tuple(launcher.SERVER_KINDS)
            unknown_bug_kinds = set(bug_backends).difference(launcher.SERVER_KINDS)
            if unknown_bug_kinds:
                raise pytest.UsageError(
                    f"{item.nodeid}: @pytest.mark.known_bug backends needs server kinds from "
                    f"{', '.join(launcher.SERVER_KINDS)}; got {bug_backends!r}"
                )
            if kind in bug_backends:
                item.add_marker(
                    pytest.mark.xfail(
                        reason=(
                            f"known bug: https://github.com/jampat000/Weir/issues/{issue} — this test asserts "
                            f"the correct behaviour, which {kind} does not implement yet"
                        ),
                        strict=True,
                    )
                )
        selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


_area_results: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    outcome = yield
    report = outcome.get_result()
    area = _area_of(item)
    if area is None:
        return
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _area_results[area][report.outcome] += 1


def pytest_terminal_summary(terminalreporter: Any) -> None:
    if not _area_results:
        return
    kind = launcher.server_kind()
    terminalreporter.section(f"Weir contract areas ({kind})")
    for area in AREAS:
        counts = _area_results.get(area["name"])
        if not counts:
            continue
        failed = counts.get("failed", 0)
        verdict = "FAIL" if failed else "PASS"
        required = "required" if kind in area.get("required", []) else "not yet required"
        terminalreporter.write_line(
            f"{verdict:4}  {area['name']:15} passed={counts.get('passed', 0)} failed={failed} "
            f"skipped={counts.get('skipped', 0)}  ({required}, port #{area.get('port_issue')})"
        )


def pytest_collection_finish(session: pytest.Session) -> None:
    leaked = sorted(name for name in sys.modules if name == "weir" or name.startswith("weir."))
    if leaked:
        raise pytest.UsageError(
            "The contract suite must not import Weir (it judges a server it cannot see inside), "
            f"but these modules were imported during collection: {', '.join(leaked[:5])}"
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    stopped = launcher.runtime.reap_leftovers()
    if stopped:
        print(f"Weir contract: stopped servers left behind by an earlier run: {', '.join(stopped)}")


# --- servers ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    """Extra environment for this module's server. Override in a module to change it."""

    return {}


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory, server_env: dict[str, str]) -> Iterator[launcher.ServerUnderTest]:
    """One server and one fresh data folder for the whole test module."""

    sut = launcher.ServerUnderTest(home=tmp_path_factory.mktemp("weir_home"), env_overrides=dict(server_env))
    try:
        sut.start()
    except RuntimeError as exc:
        pytest.fail(f"Weir contract could not start its server.\n{exc}", pytrace=False)
    try:
        yield sut
    finally:
        sut.stop()


@pytest.fixture
def server_factory(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[..., launcher.ServerUnderTest]]:
    """Make extra servers, each with its own data folder, for tests that need isolation or special env.

    ``make(env={...}, start=True, home=None)``. Every server made is stopped after the test.
    """

    made: list[launcher.ServerUnderTest] = []

    def make(
        env: dict[str, str] | None = None, *, start: bool = True, home: Path | None = None
    ) -> launcher.ServerUnderTest:
        sut = launcher.ServerUnderTest(
            home=home or tmp_path_factory.mktemp("weir_home"),
            env_overrides=dict(env or {}),
        )
        made.append(sut)
        if start:
            try:
                sut.start()
            except RuntimeError as exc:
                pytest.fail(f"Weir contract could not start its server.\n{exc}", pytrace=False)
        return sut

    try:
        yield make
    finally:
        for sut in reversed(made):
            sut.stop()


# --- clients ----------------------------------------------------------------------------------------


@pytest.fixture
def client_factory() -> Iterator[Callable[..., WeirClient]]:
    """``make(server, headers=None)`` -> a new cookie jar against ``server``; closed after the test."""

    made: list[WeirClient] = []

    def make(sut: launcher.ServerUnderTest, headers: dict[str, str] | None = None) -> WeirClient:
        c = WeirClient(sut.base_url, headers=headers)
        made.append(c)
        return c

    try:
        yield make
    finally:
        for c in made:
            c.close()


@pytest.fixture
def client(server: launcher.ServerUnderTest, client_factory: Callable[..., WeirClient]) -> WeirClient:
    """Anonymous client against the module's server."""

    return client_factory(server)


@pytest.fixture
def admin(client: WeirClient) -> WeirClient:
    """Signed in as the admin (created through bootstrap the first time)."""

    client.ensure_admin()
    return client


# --- fakes ------------------------------------------------------------------------------------------


@pytest.fixture
def fake_ffmpeg(tmp_path: Path) -> FakeFfmpeg:
    return FakeFfmpeg.install(tmp_path / "fake-ffmpeg")


@pytest.fixture
def real_ffmpeg_env() -> dict[str, str]:
    folder = real_ffmpeg_dir()
    if folder is None:
        pytest.skip("ffmpeg and ffprobe are not available")
    return {"WEIR_FFMPEG_DIR": str(folder)}


@pytest.fixture
def fake_managers() -> Iterator[Callable[..., FakeManager]]:
    """``make(kind, **preset_kwargs)`` -> a started fake (``deluno``, ``sonarr``, ``radarr``); stopped after."""

    made: list[FakeManager] = []

    def make(kind: str, **kwargs: Any) -> FakeManager:
        fake = FakeManager.deluno(**kwargs) if kind == "deluno" else FakeManager.arr(kind, **kwargs)
        made.append(fake.start())
        return fake

    try:
        yield make
    finally:
        for fake in made:
            fake.stop()


@pytest.fixture(scope="session")
def contract_backend() -> str:
    return os.environ.get("WEIR_CONTRACT_SERVER", "python")
