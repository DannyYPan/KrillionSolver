"""Site-specific configuration; selectors are intentionally unset until verified."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteAdapter:
    key: str
    label: str
    default_url: str
    prompt_selector: str | None = None


ADAPTERS = {
    "Krillion": SiteAdapter("krillion", "Krillion", "https://krillion.io/"),
    "Puffer Party": SiteAdapter("puffer-party", "Puffer Party", "https://krillion.io/party"),
}
