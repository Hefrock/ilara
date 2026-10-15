"""Dashboard link on the DOH measles page (sources S1), for link changes only.

The page embeds the Power BI dashboard by a publish-to-web link. When DOH republishes the report
the link changes and the old one stops working (2026-10-13, ADR 0009). This parser reads only the
dashboard links from the page; the runner compares them with the page captured before and
raises ``DASHBOARD_LINK_CHANGED`` when they differ, so the registry can follow DOH's own link.
It writes no data rows.
"""

from __future__ import annotations

import html
import re

PARSER_VERSION = "1.0.0"
_LINK = re.compile(r"https://app\.powerbigov\.us/view\?r=([A-Za-z0-9_\-]+={0,2})")


def dashboard_links(page: bytes) -> list[str]:
    """Distinct Power BI view links on the page, in sorted order."""
    text = html.unescape(page.decode("utf-8", "replace"))
    return sorted({f"https://app.powerbigov.us/view?r={k}" for k in _LINK.findall(text)})


def compare(current: list[str], previous: list[str] | None) -> list[tuple[str, str]]:
    """Flags for this page given the dashboard links of the page captured before it."""
    if not current:
        return [("DASHBOARD_LINK_CHANGED", "DOH measles page shows no dashboard link")]
    if previous is not None and previous != current:
        return [
            (
                "DASHBOARD_LINK_CHANGED",
                f"DOH measles page now links the dashboard at {', '.join(current)} "
                f"(before: {', '.join(previous) or 'none'}); check the registry URL",
            )
        ]
    return []
