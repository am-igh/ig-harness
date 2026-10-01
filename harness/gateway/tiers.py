"""Sensitivity tiers (rule 3). Assigned by source rules first, then pattern detectors,
then her override. The highest tier found wins. When unsure: higher tier."""
import re
from dataclasses import dataclass, field
from enum import IntEnum


class Tier(IntEnum):
    S0 = 0  # public
    S1 = 1  # internal
    S2 = 2  # confidential
    S3 = 3  # restricted

    def __str__(self) -> str:
        return self.name


# Source rules: what kind of data this is, regardless of its content.
SOURCE_TIERS: dict[str, Tier] = {
    "public_web": Tier.S0, "event_listing": Tier.S0, "newsletter": Tier.S0, "published_report": Tier.S0,
    "task": Tier.S1, "project_plan": Tier.S1, "concept_note": Tier.S1, "admin": Tier.S1,
    "email": Tier.S2, "gmail": Tier.S2, "calendar": Tier.S2, "bank_statement": Tier.S2,
    "invoice": Tier.S2, "contract": Tier.S2, "funder": Tier.S2,
    "payroll": Tier.S3, "hr": Tier.S3, "personal": Tier.S3, "credentials": Tier.S3,
}
UNKNOWN_SOURCE_TIER = Tier.S2   # when unsure, use the higher tier

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{3,5}){3,8}\b")
_AVS = re.compile(r"\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b")
_SALARY = re.compile(r"\b(salary|salaries|salaire|payroll|payslip|bulletin de paie|gehalt|lohn|13th month|treizi[eè]me|brut annuel)\b", re.I)
_HEALTH = re.compile(r"\b(diagnos\w*|maladie|medical certificate|certificat m[ée]dical|sick leave|arr[eê]t maladie|therapy|th[ée]rapie|medication|m[ée]dicament|surgery|chemotherapy)\b", re.I)
_CREDENTIAL = re.compile(r"(\b(password|passwort|mot de passe|passphrase|api[ _-]?key|secret|token)\b\s*[:=]|sk-ant-|sk-[A-Za-z0-9]{20,}|BEGIN (?:RSA |EC )?PRIVATE KEY|bearer\s+[A-Za-z0-9._-]{20,})", re.I)
_MONEY = re.compile(r"(\b(CHF|EUR|USD|GBP)\s?\d[\d'’., ]*|\d[\d'’., ]*\s?(CHF|EUR|USD|GBP|€|\$)|[€$£]\s?\d)", re.I)
_BANK = re.compile(r"\b(relev[ée] de compte|bank statement|kontoauszug|ubs|virement|wire transfer|invoice (no|number)|facture n)\b", re.I)

DETECTORS: list[tuple[str, re.Pattern, Tier]] = [
    ("iban", _IBAN, Tier.S3), ("avs-number", _AVS, Tier.S3), ("salary-or-payroll", _SALARY, Tier.S3),
    ("health", _HEALTH, Tier.S3), ("credential", _CREDENTIAL, Tier.S3),
    ("amount", _MONEY, Tier.S2), ("bank-or-invoice", _BANK, Tier.S2),
]


@dataclass
class Classification:
    tier: Tier
    reasons: list[str] = field(default_factory=list)


def classify(text: str, source: str, space: str = "work", override: Tier | None = None) -> Classification:
    """Highest tier from the source rule, the pattern detectors and her override.

    Her override can raise OR lower the tier (it is her decision), but it is applied last
    and recorded in the reasons. Personal-space items are always S3 and cannot be lowered.
    """
    base = SOURCE_TIERS.get(source)
    tier = base if base is not None else UNKNOWN_SOURCE_TIER
    reasons = [f"source:{source}" if base is not None else f"source:{source} (unknown, so higher tier)"]
    for name, pat, t in DETECTORS:
        if pat.search(text) and t > tier:
            tier = t
        if pat.search(text):
            reasons.append(f"detected:{name}")
    if space == "personal":
        tier = Tier.S3
        reasons.append("personal space")
    elif override is not None:
        tier = override
        reasons.append(f"override:{override}")
    return Classification(tier, reasons)
