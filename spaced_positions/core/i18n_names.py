"""Names made from identifiers, shared by the Settings mode and the catalogue extraction (core/i18n_catalog.py)."""


def token_label(name: str) -> str:
    """The Settings row label of a design token: `sq-light` → `Sq light`."""
    return name.replace("-", " ").capitalize()
