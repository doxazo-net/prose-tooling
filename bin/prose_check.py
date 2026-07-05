"""prose_check -- Markdown-aware grammar/prose lint client for LanguageTool.

See docs/superpowers/specs/2026-07-05-cross-repo-grammar-tooling-design.md.

Location mapping (per-block engine): Markdown is split into prose blocks, each
tagged with its source line. The blocks are joined into ONE pure-prose string
(no markup) and checked in a single request; because the checked string
contains no markup, LanguageTool's offsets cannot drift against it, and each
offset maps back to a source line via the block it falls in.
"""

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from markdown_it import MarkdownIt

# commonmark plus the GFM table rule, so table syntax is structure (excluded),
# not prose. (Plain commonmark would leak `|`/`---` rows as text.) We avoid the
# full gfm-like preset because it enables linkify, which needs an extra package.
_MD = MarkdownIt("commonmark").enable("table")

# A leading YAML frontmatter block: `---` on line 1, prose lines, closing `---`.
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def _strip_frontmatter(markdown_text):
    """Return (body, leading_line_count) with any YAML frontmatter removed."""
    match = _FRONTMATTER_RE.match(markdown_text)
    if not match:
        return markdown_text, 0
    return markdown_text[match.end():], match.group(0).count("\n")


class Block:
    """A run of prose plus the source line its first character sits on.

    ``text`` is the reconstructed prose sent to the server (inline code becomes
    a space, markup dropped). ``children`` is the list of (raw_text, line) for
    each source text child -- used by the local rules, which must see genuine
    source whitespace, not the reconstruction's artifacts.
    """

    __slots__ = ("text", "base_line", "children")

    def __init__(self, text, base_line, children):
        self.text = text
        self.base_line = base_line
        self.children = children

    def line_of(self, offset):
        """Source line of a character offset within this block's text."""
        return self.base_line + self.text.count("\n", 0, offset)


def extract_blocks(markdown_text):
    """Split Markdown into prose Blocks, each tagged with its source line."""
    body, frontmatter_lines = _strip_frontmatter(markdown_text)
    blocks = []
    for token in _MD.parse(body):
        if token.type != "inline":
            continue
        base_line = (token.map[0] if token.map else 0) + frontmatter_lines + 1
        parts = []
        children = []
        line = base_line
        for child in token.children or []:
            kind = child.type
            if kind == "text":
                parts.append(child.content)
                children.append((child.content, line))
            elif kind in ("softbreak", "hardbreak"):
                parts.append("\n")
                line += 1
            elif kind == "code_inline":
                parts.append(" ")  # word separation without checking the code
            # link/em/strong markers, link URLs, images, html: contribute nothing
        text = "".join(parts)
        if text.strip():
            blocks.append(Block(text, base_line, children))
    return blocks


def combine_blocks(blocks):
    """Join blocks into one prose string; return (text, spans).

    spans is a list of (start, end, block) so an offset into the combined text
    maps back to the owning block. Blocks are separated by a blank line so
    LanguageTool treats them as distinct sentences.
    """
    parts = []
    spans = []
    pos = 0
    for block in blocks:
        start = pos
        parts.append(block.text)
        pos += len(block.text)
        spans.append((start, pos, block))
        parts.append("\n\n")
        pos += 2
    return "".join(parts), spans


def line_for_offset(spans, offset):
    """Map a combined-text offset back to a source line via its block."""
    previous = None
    for start, end, block in spans:
        if start <= offset < end:
            return block.line_of(offset - start)
        if offset >= start:
            previous = block
    # Offset landed in a block-separator gap: use the preceding block's end.
    if previous is not None:
        return previous.line_of(len(previous.text))
    return None


# --------------------------------------------------------------------------
# Client-side local rules for house rules the free server does not cover.
# --------------------------------------------------------------------------
_EM_DASH_RE = re.compile("—")
_DOUBLE_SPACE_RE = re.compile(r"(?<=[.!?]) {2,}")


def _local_match(rule_id, offset, length, message, replacements):
    return {
        "rule": {"id": rule_id, "category": {"id": "LOCAL"}},
        "offset": offset,
        "length": length,
        "message": message,
        "replacements": [{"value": r} for r in replacements],
    }


def local_matches_text(text):
    """Scan a prose string for house rules with no free-server rule."""
    matches = []
    for m in _EM_DASH_RE.finditer(text):
        matches.append(
            _local_match(
                "LOCAL_EM_DASH",
                m.start(),
                m.end() - m.start(),
                "Em-dash: prefer a dash, comma, or parentheses.",
                ["-"],
            )
        )
    for m in _DOUBLE_SPACE_RE.finditer(text):
        matches.append(
            _local_match(
                "LOCAL_DOUBLE_SPACE",
                m.start(),
                m.end() - m.start(),
                "Use a single space after sentence-ending punctuation.",
                [" "],
            )
        )
    return matches


_SPELLING_CATEGORY = "TYPOS"


def filter_allowlisted(matches, text, allowlist):
    """Drop spelling matches whose flagged word is in the allowlist."""
    kept = []
    for match in matches:
        category = match.get("rule", {}).get("category", {}).get("id")
        if category == _SPELLING_CATEGORY:
            start = match["offset"]
            word = text[start : start + match["length"]]
            if word.lower() in allowlist:
                continue
        kept.append(match)
    return kept


def partition_matches(matches, blocking_ids):
    """Split matches into (blocking, advisory) by rule ID or category ID."""
    blocking, advisory = [], []
    for match in matches:
        rule = match.get("rule", {})
        if rule.get("id") in blocking_ids or rule.get("category", {}).get("id") in blocking_ids:
            blocking.append(match)
        else:
            advisory.append(match)
    return blocking, advisory


# --------------------------------------------------------------------------
# Config, server I/O, and CLI.
# --------------------------------------------------------------------------
DEFAULT_SERVER = os.environ.get("PROSE_LINT_SERVER", "http://localhost:8081")
_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_SERVER_SCRIPT = Path(__file__).resolve().parent / "prose-lint-server.sh"


def _read_wordlist(path):
    if not path.exists():
        return set()
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return words


def load_bundle(config_dir, lang):
    """Load the severity.toml bundle for a language plus its merged allowlist."""
    config_dir = Path(config_dir)
    with open(config_dir / lang / "severity.toml", "rb") as handle:
        bundle = tomllib.load(handle)
    bundle.setdefault("language", lang)
    bundle.setdefault("level", "picky")
    for key in ("enabled_rules", "disabled_rules", "disabled_categories", "blocking"):
        bundle.setdefault(key, [])
    bundle["allowlist"] = _read_wordlist(config_dir / "dictionary.txt") | _read_wordlist(
        config_dir / lang / "dictionary.txt"
    )
    return bundle


class ServerUnreachable(RuntimeError):
    pass


def server_is_up(server):
    """True if the LanguageTool server answers /v2/languages."""
    try:
        with urllib.request.urlopen(server.rstrip("/") + "/v2/languages", timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _start_server():
    """Start the container via the server script (blocks until ready)."""
    import subprocess

    subprocess.run([str(_SERVER_SCRIPT), "start"], check=False)


def ensure_server(server, start_fn=_start_server, is_up=server_is_up):
    """Ensure the server is reachable, starting it once if it is not."""
    if is_up(server):
        return True
    start_fn()
    return is_up(server)


def _post_check(server, text, bundle):
    fields = {
        "text": text,
        "language": bundle["language"],
        "level": bundle["level"],
    }
    if bundle["enabled_rules"]:
        fields["enabledRules"] = ",".join(bundle["enabled_rules"])
    if bundle["disabled_rules"]:
        fields["disabledRules"] = ",".join(bundle["disabled_rules"])
    if bundle["disabled_categories"]:
        fields["disabledCategories"] = ",".join(bundle["disabled_categories"])
    data = urllib.parse.urlencode(fields).encode()
    url = server.rstrip("/") + "/v2/check"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as resp:
            return json.load(resp).get("matches", [])
    except (urllib.error.URLError, OSError) as exc:
        raise ServerUnreachable(str(exc)) from exc


def check_markdown(markdown_text, server, bundle):
    """Return findings for one document: match dicts each with a `line` set."""
    blocks = extract_blocks(markdown_text)
    combined, spans = combine_blocks(blocks)
    findings = []
    if combined.strip():
        matches = _post_check(server, combined, bundle)
        matches = filter_allowlisted(matches, combined, bundle["allowlist"])
        for match in matches:
            enriched = dict(match)
            enriched["line"] = line_for_offset(spans, match.get("offset", 0))
            findings.append(enriched)
    # Local rules scan the RAW text children (genuine source whitespace), not
    # the reconstructed block, so inline-code removal cannot fabricate findings.
    for block in blocks:
        for content, line in block.children:
            for match in local_matches_text(content):
                enriched = dict(match)
                enriched["line"] = line
                findings.append(enriched)
    findings.sort(key=lambda f: (f["line"] or 0, f.get("offset", 0)))
    return findings


def _format_finding(path, finding, severity):
    rule_id = finding.get("rule", {}).get("id", "?")
    message = finding.get("message", "")
    reps = finding.get("replacements") or []
    suggestion = f"  (suggest: {reps[0].get('value', '')!r})" if reps else ""
    return f"{path}:{finding.get('line')}: [{severity}] {rule_id} {message}{suggestion}"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description="Markdown-aware grammar/prose lint via a local LanguageTool server."
    )
    parser.add_argument("files", nargs="*", help="Markdown/text files to check")
    parser.add_argument("--lang", default="en-US")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--config-dir", default=str(_DEFAULT_CONFIG_DIR))
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="do not try to start the LanguageTool container if it is down",
    )
    args = parser.parse_args(argv)

    bundle = load_bundle(args.config_dir, args.lang)
    blocking_ids = set(bundle["blocking"])
    had_blocking = False

    if not args.no_autostart and args.files and not ensure_server(args.server):
        print(
            f"prose-check: LanguageTool server unreachable at {args.server} "
            "and could not be started.",
            file=sys.stderr,
        )
        print("Start it manually with: bin/prose-lint-server.sh start", file=sys.stderr)
        return 2

    for path in args.files:
        try:
            markdown_text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"prose-check: cannot read {path}: {exc}", file=sys.stderr)
            had_blocking = True
            continue
        try:
            findings = check_markdown(markdown_text, args.server, bundle)
        except ServerUnreachable as exc:
            print(
                f"prose-check: LanguageTool server unreachable at {args.server}: {exc}",
                file=sys.stderr,
            )
            print("Start it with: bin/prose-lint-server.sh start", file=sys.stderr)
            return 2
        blocking, advisory = partition_matches(findings, blocking_ids)
        for finding in blocking:
            print(_format_finding(path, finding, "ERROR"))
        for finding in advisory:
            print(_format_finding(path, finding, "warn"))
        if blocking:
            had_blocking = True

    return 1 if had_blocking else 0


if __name__ == "__main__":
    sys.exit(main())
