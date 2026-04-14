# linkedin/actions/connections.py
"""Scrape the My Network → Connections page to detect accepted invitations in bulk."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator

from linkedin.browser.nav import goto_page
from linkedin.db.urls import url_to_public_id

logger = logging.getLogger(__name__)

CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"

# "Connected on April 14, 2026" / "Connected on Apr 14, 2026"
_CONNECTED_ON_RE = re.compile(r"^\s*Connected on\s+(.+?)\s*$")


@dataclass(frozen=True)
class ConnectionEntry:
    public_id: str
    name: str
    connected_on: date | None


def _parse_connected_on(text: str) -> date | None:
    m = _CONNECTED_ON_RE.match(text or "")
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    logger.debug("Could not parse connected_on date: %r", raw)
    return None


def _oldest_connected_on(session) -> date | None:
    """Return the oldest 'Connected on' date currently rendered on the page."""
    texts = session.page.locator("p", has_text="Connected on").all_inner_texts()
    dates = [d for d in (_parse_connected_on(t) for t in texts) if d is not None]
    return min(dates) if dates else None


def _scroll_to_bottom(
    session,
    stop_before: date | None = None,
    max_idle_rounds: int = 3,
    pause_ms: int = 800,
) -> None:
    """Scroll until either the page stops growing or we pass *stop_before*.

    *stop_before*: the earliest connected_on date we still care about. The
    connections list is sorted newest-first, so once the oldest rendered card
    is older than this cutoff, no further scrolling can surface a match.
    """
    page = session.page
    idle = 0
    last_height = 0
    while idle < max_idle_rounds:
        if stop_before is not None:
            oldest = _oldest_connected_on(session)
            if oldest is not None and oldest < stop_before:
                logger.debug(
                    "Early-stop scroll: oldest rendered %s < cutoff %s", oldest, stop_before,
                )
                return

        height = page.evaluate("document.body.scrollHeight")
        if height == last_height:
            idle += 1
        else:
            idle = 0
            last_height = height
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(pause_ms)


def _iter_cards(session) -> Iterator[ConnectionEntry]:
    """Yield one ConnectionEntry per connection card on the page."""
    page = session.page
    # Anchor: any <p> whose text starts with "Connected on ". From there walk up
    # to the nearest ancestor that contains a profile anchor (a[href*="/in/"]).
    date_nodes = page.locator("p", has_text="Connected on").all()
    seen: set[str] = set()
    for node in date_nodes:
        try:
            connected_text = node.inner_text(timeout=2000)
        except Exception:
            continue
        connected_on = _parse_connected_on(connected_text)

        card = node.locator(
            "xpath=ancestor::*[.//a[contains(@href, '/in/')]][1]",
        )
        if card.count() == 0:
            continue
        card = card.first

        link = card.locator('a[href*="/in/"]').first
        try:
            href = link.get_attribute("href", timeout=2000) or ""
        except Exception:
            continue

        public_id = url_to_public_id(href)
        if not public_id or public_id in seen:
            continue
        seen.add(public_id)

        name = ""
        name_p = link.locator("p").first
        if name_p.count() > 0:
            try:
                name = name_p.inner_text(timeout=2000).strip()
            except Exception:
                pass

        yield ConnectionEntry(public_id=public_id, name=name, connected_on=connected_on)


def scrape_connections(
    session, stop_before: date | None = None,
) -> list[ConnectionEntry]:
    """Navigate to the connections page, scroll to load entries, return them.

    *stop_before*: earliest connected_on date of interest. Passing this lets
    the scroll bail early on accounts with huge networks instead of loading
    every connection in history.
    """
    session.ensure_browser()
    page = session.page

    goto_page(
        session,
        action=lambda: page.goto(CONNECTIONS_URL),
        expected_url_pattern="/mynetwork/invite-connect/connections",
        error_message="Failed to load My Network → Connections",
    )
    session.wait()
    _scroll_to_bottom(session, stop_before=stop_before)

    entries = list(_iter_cards(session))
    logger.info("Scraped %d connections from %s", len(entries), CONNECTIONS_URL)
    return entries
