"""prose_check -- Markdown-aware grammar/prose lint client for LanguageTool.

See docs/superpowers/specs/2026-07-05-cross-repo-grammar-tooling-design.md.
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

_MD = MarkdownIt("commonmark")

# A leading YAML frontmatter block: `---` on line 1, prose config lines, a
# closing `---`. commonmark does not parse it, so strip it before checking.
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def _strip_frontmatter(markdown_text):
    """Return (body, leading_line_count) with any YAML frontmatter removed.

    The line count preserves later source-line mapping into the body.
    """
    match = _FRONTMATTER_RE.match(markdown_text)
    if not match:
        return markdown_text, 0
    block = match.group(0)
    return markdown_text[match.end():], block.count("\n")


def build_annotation(markdown_text):
    """Convert Markdown into a LanguageTool `data` annotation segment list.

    Prose is emitted as ``{"text": ...}`` segments; Markdown syntax and code
    are emitted as ``{"markup": ...}`` so LanguageTool never checks them.
    Block boundaries become ``{"markup": "\\n\\n", "interpretAs": "\\n\\n"}``
    so LanguageTool treats separate blocks as separate sentences.
    """
    segments = []
    body, frontmatter_lines = _strip_frontmatter(markdown_text)
    tokens = _MD.parse(body)
    for token in tokens:
        if token.type == "inline":
            # token.map[0] is the 0-indexed start line of this block within the
            # body; add back stripped frontmatter lines, and track soft/hard
            # breaks so each text piece gets its true source line.
            base_line = (token.map[0] if token.map else 0) + frontmatter_lines
            line_offset = 0
            for child in token.children or []:
                if child.type == "text":
                    segments.append(
                        {"text": child.content, "_line": base_line + line_offset + 1}
                    )
                elif child.type == "softbreak":
                    segments.append({"markup": "\n", "interpretAs": " "})
                    line_offset += 1
                elif child.type == "hardbreak":
                    segments.append({"markup": "\n", "interpretAs": "\n"})
                    line_offset += 1
                else:
                    # code_inline, em/strong markers, links, images, html
                    segments.append({"markup": child.markup or child.content})
        elif token.type in ("fence", "code_block", "html_block"):
            segments.append({"markup": token.content})
        elif token.block and token.nesting in (1, -1):
            # opening/closing structural token (paragraph, heading, list, ...)
            segments.append({"markup": "\n\n", "interpretAs": "\n\n"})
    return segments


_LT_KEYS = ("text", "markup", "interpretAs")


def _contribution(segment):
    """The text a segment contributes to LanguageTool's reconstructed text."""
    if "text" in segment:
        return segment["text"]
    if "interpretAs" in segment:
        return segment["interpretAs"]
    return ""


def reconstruct_text(segments):
    """The plain text LanguageTool checks (offsets are relative to this)."""
    return "".join(_contribution(s) for s in segments)


def map_offset_to_line(segments, offset):
    """Map an offset into the reconstructed text back to a source line.

    Offsets landing inside a `text` segment return that segment's source line;
    offsets in an `interpretAs` gap between blocks return the most recent
    text segment's line.
    """
    pos = 0
    last_line = None
    for segment in segments:
        contribution = _contribution(segment)
        end = pos + len(contribution)
        if "text" in segment:
            last_line = segment["_line"]
            if pos <= offset < end:
                return segment["_line"]
        elif pos <= offset < end:
            return last_line
        pos = end
    return last_line


# Client-side local rules for house rules the free server does not cover.
_EM_DASH_RE = re.compile("—")  # em-dash
_DOUBLE_SPACE_RE = re.compile(r"(?<=[.!?]) {2,}")  # >1 space after sentence end


def _local_match(rule_id, offset, length, message, replacements):
    return {
        "rule": {"id": rule_id, "category": {"id": "LOCAL"}},
        "offset": offset,
        "length": length,
        "message": message,
        "replacements": [{"value": r} for r in replacements],
    }


def local_matches(segments):
    """Scan text segments for house rules with no free-server LanguageTool rule.

    Emits LanguageTool-shaped matches (offsets into the reconstructed text, so
    they flow through the same map/partition pipeline). Scanning per text
    segment avoids treating a block-joining ``\\n\\n`` as a sentence gap.
    """
    matches = []
    pos = 0
    for segment in segments:
        contribution = _contribution(segment)
        if "text" in segment:
            for m in _EM_DASH_RE.finditer(contribution):
                matches.append(
                    _local_match(
                        "LOCAL_EM_DASH",
                        pos + m.start(),
                        m.end() - m.start(),
                        "Em-dash: prefer a dash, comma, or parentheses.",
                        ["-"],
                    )
                )
            for m in _DOUBLE_SPACE_RE.finditer(contribution):
                matches.append(
                    _local_match(
                        "LOCAL_DOUBLE_SPACE",
                        pos + m.start(),
                        m.end() - m.start(),
                        "Use a single space after sentence-ending punctuation.",
                        [" "],
                    )
                )
        pos += len(contribution)
    return matches


_SPELLING_CATEGORY = "TYPOS"


def filter_allowlisted(matches, reconstructed_text, allowlist):
    """Drop spelling matches whose flagged word is in the allowlist.

    Only TYPOS-category (spelling) matches are eligible; grammar/style matches
    are never filtered. Comparison is case-insensitive.
    """
    kept = []
    for match in matches:
        category = match.get("rule", {}).get("category", {}).get("id")
        if category == _SPELLING_CATEGORY:
            start = match["offset"]
            word = reconstructed_text[start : start + match["length"]]
            if word.lower() in allowlist:
                continue
        kept.append(match)
    return kept


def to_lt_payload(segments):
    """Serialize segments to the LanguageTool `data` payload (no internal keys)."""
    annotation = [
        {key: seg[key] for key in _LT_KEYS if key in seg} for seg in segments
    ]
    return {"annotation": annotation}


def partition_matches(matches, blocking_ids):
    """Split LanguageTool matches into (blocking, advisory).

    A match blocks if its rule ID or its rule's category ID is in
    ``blocking_ids``; otherwise it is advisory. Order is preserved.
    """
    blocking, advisory = [], []
    for match in matches:
        rule = match.get("rule", {})
        rule_id = rule.get("id")
        category_id = rule.get("category", {}).get("id")
        if rule_id in blocking_ids or category_id in blocking_ids:
            blocking.append(match)
        else:
            advisory.append(match)
    return blocking, advisory


# --------------------------------------------------------------------------
# Config loading, server I/O, and CLI. (I/O layer -- the pure logic above is
# unit-tested; this layer is covered by the live integration test.)
# --------------------------------------------------------------------------

DEFAULT_SERVER = os.environ.get("PROSE_LINT_SERVER", "http://localhost:8081")
_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


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


def _post_check(server, payload, bundle):
    fields = {
        "data": json.dumps(payload),
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
    """Return (segments, matches) for one Markdown document.

    Combines server matches with client-side local rules, drops allowlisted
    spellings, and sorts by position.
    """
    segments = build_annotation(markdown_text)
    reconstructed = reconstruct_text(segments)
    matches = _post_check(server, to_lt_payload(segments), bundle)
    matches += local_matches(segments)
    matches = filter_allowlisted(matches, reconstructed, bundle["allowlist"])
    matches.sort(key=lambda m: m.get("offset", 0))
    return segments, matches


def _format_finding(path, segments, match, severity):
    line = map_offset_to_line(segments, match.get("offset", 0))
    rule_id = match.get("rule", {}).get("id", "?")
    message = match.get("message", "")
    suggestion = ""
    reps = match.get("replacements") or []
    if reps:
        suggestion = f"  (suggest: {reps[0].get('value', '')!r})"
    return f"{path}:{line}: [{severity}] {rule_id} {message}{suggestion}"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description="Markdown-aware grammar/prose lint via a local LanguageTool server."
    )
    parser.add_argument("files", nargs="*", help="Markdown/text files to check")
    parser.add_argument("--lang", default="en-US")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--config-dir", default=str(_DEFAULT_CONFIG_DIR))
    args = parser.parse_args(argv)

    bundle = load_bundle(args.config_dir, args.lang)
    blocking_ids = set(bundle["blocking"])
    had_blocking = False

    for path in args.files:
        try:
            markdown_text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"prose-check: cannot read {path}: {exc}", file=sys.stderr)
            had_blocking = True
            continue
        try:
            segments, matches = check_markdown(markdown_text, args.server, bundle)
        except ServerUnreachable as exc:
            # Fail loud: an installed checker with a dead server must never
            # silently pass a commit.
            print(
                f"prose-check: LanguageTool server unreachable at {args.server}: {exc}",
                file=sys.stderr,
            )
            print("Start it with: bin/prose-lint-server.sh start", file=sys.stderr)
            return 2
        blocking, advisory = partition_matches(matches, blocking_ids)
        for match in blocking:
            print(_format_finding(path, segments, match, "ERROR"))
        for match in advisory:
            print(_format_finding(path, segments, match, "warn"))
        if blocking:
            had_blocking = True

    return 1 if had_blocking else 0


if __name__ == "__main__":
    sys.exit(main())
