"""The shipped examples/ starters must always be valid so adopters can copy them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))

from prose_check import load_bundle, load_i18n_ignore

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_example_bundles_load():
    for bundle in ("en-US", "en-US-microcopy"):
        b = load_bundle(EXAMPLES / "config", bundle)
        assert b["language"] == "en-US"
        assert isinstance(b["blocking"], list) and b["blocking"]


def test_example_prose_lint_toml_parses():
    keys = load_i18n_ignore(EXAMPLES / ".prose-lint.toml")
    assert isinstance(keys, list)
