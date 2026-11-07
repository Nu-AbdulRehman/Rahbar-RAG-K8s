"""Reading the question before retrieval (section 3.2 step 4)."""

from __future__ import annotations

import re

# Superseded documents are filtered out unless the question explicitly asks for an older
# version (DECISIONS.md D17): an "old" word next to a document word ("the previous
# handbook"), or a year attached to a document word ("the 2023 rules", "rules from 2023").
# "previous semester" or "last year" alone do not count. Naming a year only widens the
# filter: current documents are still searched and ranked alongside the old ones.
OLD_WORD = r"(old|older|previous|earlier|prior|former|superseded|outdated|repealed)"
DOC_WORD = r"(version|edition|rules?|handbook|policy|policies|regulations?|prospectus)"
YEAR = r"20\d\d"
OLDER_VERSION = re.compile(
    rf"\b{OLD_WORD}\s+(\w+\s+){{0,2}}{DOC_WORD}\b"
    rf"|\b{DOC_WORD}\s+(of|from|in)\s+{YEAR}\b"
    rf"|\b{YEAR}\s+(\w+\s+)?{DOC_WORD}\b",
    re.I,
)


def asks_about_older_version(question: str) -> bool:
    return bool(OLDER_VERSION.search(question))
