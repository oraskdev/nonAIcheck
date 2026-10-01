"""Inspect invisible formatting without mistaking it for proof of AI authorship."""
import unicodedata
from collections import Counter

# These affect formatting, not spelling. Language joiners and bidi controls stay intact.
REMOVABLE = {"\ufeff", "\u00ad", "\u2060"}


def audit(blocks):
    counts = Counter(c for b in blocks for c in b["text"] if unicodedata.category(c) == "Cf")
    return {
        "total": sum(counts.values()),
        "removable": sum(n for c, n in counts.items() if c in REMOVABLE),
        "characters": [{"code": f"U+{ord(c):04X}", "name": unicodedata.name(c, "FORMAT CHARACTER"), "count": n, "removable": c in REMOVABLE} for c, n in sorted(counts.items())],
        "notice": "Formatting characters are not proof of an AI watermark. Language joiners and bidirectional controls are preserved. Statistical text watermarks are not assessed.",
    }


def clean(blocks):
    return [{**b, "text": "".join(c for c in b["text"] if c not in REMOVABLE)} for b in blocks]
