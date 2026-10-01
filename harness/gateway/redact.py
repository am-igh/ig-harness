"""Replace identifiers with placeholders before anything leaves the Mac (rule 4).
The mapping stays local. Names are replaced from a list of known names (e.g. the Suivi People sheet)."""
import re
from dataclasses import dataclass, field

from harness.gateway.tiers import _AVS, _IBAN

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+|00)\d{1,3}[\s.-]?\(?\d{1,3}\)?(?:[\s.-]?\d{2,4}){2,4}(?!\d)")
_AMOUNT = re.compile(r"(\b(?:CHF|EUR|USD|GBP)\s?\d[\d'’., ]*\d|\d[\d'’., ]*\d\s?(?:CHF|EUR|USD|GBP|€|\$)|[€$£]\s?\d[\d'’., ]*\d)", re.I)
_URL = re.compile(r"https?://\S+")


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)   # placeholder -> original (local only)

    def restore(self, text: str) -> str:
        for ph, orig in self.mapping.items():
            text = text.replace(ph, orig)
        return text


def redact(text: str, known_names: tuple[str, ...] = ()) -> Redaction:
    mapping: dict[str, str] = {}
    seen: dict[str, str] = {}
    counters: dict[str, int] = {}

    def sub(kind: str):
        def _r(m: re.Match) -> str:
            orig = m.group(0)
            if orig in seen:
                return seen[orig]
            counters[kind] = counters.get(kind, 0) + 1
            ph = f"[{kind}_{counters[kind]}]"
            mapping[ph] = orig
            seen[orig] = ph
            return ph
        return _r

    # Order matters: longest/most specific identifiers first.
    for kind, pat in (("URL", _URL), ("EMAIL", _EMAIL), ("IBAN", _IBAN), ("AVS", _AVS), ("AMOUNT", _AMOUNT), ("PHONE", _PHONE)):
        text = pat.sub(sub(kind), text)
    for name in sorted({n for n in known_names if n and len(n) > 2}, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", sub("PERSON"), text, flags=re.I)
    return Redaction(text, mapping)
