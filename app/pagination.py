"""Utilities for GitHub Link pagination headers."""

# Author: Sagar — GitHub pagination header parsing.

import re

LINK_PATTERN = re.compile(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"')


def parse_link_header(value: str | None) -> dict[str, str]:
    """Return GitHub pagination URLs keyed by relation name."""
    if not value:
        return {}

    links: dict[str, str] = {}
    for part in value.split(","):
        match = LINK_PATTERN.fullmatch(part.strip())
        if match:
            url, relation = match.groups()
            links[relation] = url
    return links
