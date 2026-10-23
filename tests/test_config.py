"""App-wide constants."""

import re

from recon import config


def test_app_id_is_reverse_dns() -> None:
    assert config.APP_ID == "io.github.tylerlight071.Recon"
    assert re.fullmatch(r"[a-z]+(\.[a-z0-9]+)+\.[A-Z][A-Za-z]+", config.APP_ID)
