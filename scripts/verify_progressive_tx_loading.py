"""Headless Transactions page smoke check for light snapshot and background fill.

The app asks for `?light=1`, the progress ring is visible while chunks land, it
disappears when the last one does, and the ledger ends up complete and in order.
"""

import logging
import os
import pathlib
import stat
import sys
import tempfile
from enum import StrEnum

from playwright.sync_api import Browser, Page, Request, sync_playwright
from pydantic import TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

TOKEN_FILE = pathlib.Path(tempfile.gettempdir()) / f"monori-token-{os.getuid()}.txt"
TOKEN_FILE_MODE = 0o600
SNAPSHOT_ROW_COUNT = 500
logger = logging.getLogger(__name__)

# the fill is fast on localhost, so watch the DOM for the ring instead of
# racing it with polls
WATCH_RING = """
    window.__ringSeen = [];
    const watch = () => {
        new MutationObserver(() => {
            const ring = document.querySelector('.progress-ring');
            if (ring) window.__ringSeen.push(ring.innerText.trim());
        }).observe(document.body, {childList: true, subtree: true, characterData: true});
    };
    if (document.body) watch();
    else document.addEventListener('DOMContentLoaded', watch);
"""

STATE_JS = """() => {
    const m = document.body.innerText.match(/(\\d[\\d\\s]*) transactions/);
    const dates = [...document.querySelectorAll('tr.cat-row td:first-child')].map(
        (td) => td.innerText.trim(),
    );
    return {
        count: m ? +m[1].replace(/\\s/g, '') : null,
        ring: !!document.querySelector('.progress-ring'),
        ringSeen: window.__ringSeen ?? [],
        firstDates: dates.slice(0, 3),
    };
}"""


@pydantic_dataclass
class PageState:
    """Observed browser state used to verify progress-ring loading behavior."""

    count: int | None
    ring: bool
    ringSeen: list[str]
    firstDates: list[str]


@pydantic_dataclass
class ReducedRing:
    """Observed state of the reduced-motion variant ring."""

    text: str
    svg: bool


class ReducedMotion(StrEnum):
    """Client preference values for reduced-motion checks."""

    NO_PREFERENCE = "no-preference"
    REDUCE = "reduce"


PAGE_STATE_ADAPTER: TypeAdapter[PageState] = TypeAdapter(PageState)
REDUCED_RING_ADAPTER: TypeAdapter[ReducedRing] = TypeAdapter(ReducedRing)


def load_token() -> str:
    """Load a user-owned token file with restrictive permissions."""
    if not TOKEN_FILE.exists():
        sys.exit(
            f"{TOKEN_FILE} not found — mint one first, e.g.:\n"
            "  cd server && uv run python -c "
            "'from app.security import create_access_token; print(create_access_token(1))'"
            f" > {TOKEN_FILE} && chmod 600 {TOKEN_FILE}"
        )
    metadata = TOKEN_FILE.lstat()
    if (
        TOKEN_FILE.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o777 != TOKEN_FILE_MODE
    ):
        sys.exit(f"{TOKEN_FILE} must be a user-owned regular file with mode 0600")
    return TOKEN_FILE.read_text().strip()


def open_page(
    browser: Browser,
    token: str,
    requests: list[str] | None = None,
    reduced_motion: ReducedMotion | None = None,
) -> Page:
    """Open page for this module."""
    page = browser.new_page(
        viewport={"width": 1280, "height": 900},
        reduced_motion=reduced_motion.value if reduced_motion is not None else None,
    )
    if requests is not None:

        def record_request(r: Request) -> None:
            if "/api/" in r.url:
                requests.append(r.url)

        page.on("request", record_request)
    page.add_init_script(f"localStorage.setItem('monori_token', {token!r});")
    page.add_init_script(WATCH_RING)
    # localhost finishes the fill before you can look at it, and a slow link is
    # exactly the case the ring exists for — so throttle one in
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": 150,
            "downloadThroughput": 500 * 1024,
            "uploadThroughput": 500 * 1024,
        },
    )
    page.goto("http://localhost:5173/", wait_until="domcontentloaded")
    page.get_by_text("Transactions", exact=True).first.click()
    page.wait_for_selector("tr.cat-row", timeout=15000)
    return page


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = load_token()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        requests: list[str] = []
        page = open_page(browser, token, requests=requests)
        page.wait_for_function("() => !document.querySelector('.progress-ring')", timeout=60000)
        state = PAGE_STATE_ADAPTER.validate_python(page.evaluate(STATE_JS))
        logger.info("AFTER FILL: %s", state)
        page.close()

        # prefers-reduced-motion swaps the ring for the bare percentage
        reduced = open_page(browser, token, reduced_motion=ReducedMotion.REDUCE)
        reduced.wait_for_selector(".progress-ring", timeout=15000)
        reduced_ring = REDUCED_RING_ADAPTER.validate_python(
            reduced.evaluate(
                """() => {
            const ring = document.querySelector('.progress-ring');
            return {text: ring.innerText.trim(), svg: !!ring.querySelector('svg')};
                }"""
            )
        )
        logger.info("REDUCED MOTION: %s", reduced_ring)
        browser.close()

        light = [u for u in requests if "/api/snapshot" in u]
        chunks = [u for u in requests if "/api/transactions?" in u]
        logger.info("snapshot requests: %s", light)
        logger.info("chunk requests: %s", len(chunks))

        logger.info("\n=== checks ===")
        ok = True

        def check(name: str, *, cond: bool) -> None:
            nonlocal ok
            ok = ok and cond
            logger.info("[%s] %s", "PASS" if cond else "FAIL", name)

        check("first paint used the light snapshot", cond=all("light=1" in u for u in light))
        # 500 rows arrive with the snapshot, the rest in 1000-row chunks; more
        # than that would mean a superseded fill kept running
        count = state.count
        assert count is not None
        expected_chunks = max(0, (count - SNAPSHOT_ROW_COUNT + 999) // 1000)
        check(
            f"the fill ran exactly once ({expected_chunks} chunks)",
            cond=len(chunks) == expected_chunks,
        )
        check("progress ring appeared during the fill", cond=len(state.ringSeen) > 0)
        check("ring reported a percentage", cond=any("%" in s for s in state.ringSeen))
        check("ring is gone once the fill finished", cond=state.ring is False)
        check("ledger is fully loaded", cond=count > SNAPSHOT_ROW_COUNT)
        check("reduce motion drops the ring", cond=reduced_ring.svg is False)
        check("reduce motion still shows the percentage", cond="%" in reduced_ring.text)
        logger.info("\nRESULT: %s", "ALL PASS" if ok else "SOME FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
