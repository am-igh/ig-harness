"""How Anne-Marie writes to each person, learned from her past messages. Plain rules, no model: every
result can be explained ("3 of 4 messages start with 'Dear {name},'") and corrected by her.

Used by drafting: language, formal or informal ("vous" or "tu"), usual greeting and closing, typical length.
A person with no history gets the professional default instead."""
import re
import sqlite3
from collections import Counter

STOPWORDS = {
    "en": set("the and to of in is that for with on this are as be have you your we will would please thank thanks best regards hi dear it at from by can our".split()),
    "fr": set("le la les des et de du que est pour dans nous vous votre vos avec merci bonjour cordialement je ce une un pas sur au aux sera avons nos ont suis très".split()),
    "de": set("der die das und ist nicht mit für ich wir sie ihr ihre bitte danke guten freundliche grüße grüsse zu den von auf dem ein eine sind haben".split()),
    "it": set("il lo gli della che per con grazie cordiali saluti buongiorno sono non una nel dei delle siamo abbiamo".split()),
    "es": set("el los las que para con por gracias saludos buenos estimado una del nuestro estamos hemos".split()),
}
CLOSINGS = re.compile(
    r"^(best regards|kind regards|warm regards|best wishes|with best wishes|regards|best|cheers|thanks|thank you|many thanks|sincerely|yours sincerely|yours faithfully|"
    r"cordialement|bien cordialement|très cordialement|meilleures salutations|salutations distinguées|salutations|bien à vous|amicalement|à bientôt|bien amicalement|"
    r"mit freundlichen grüssen|mit freundlichen grüßen|freundliche grüsse|freundliche grüße|beste grüsse|beste grüße|viele grüsse|viele grüße|herzliche grüsse|"
    r"cordiali saluti|saluti|un saludo|saludos|atentamente)\b[\s,.!;:-]*$", re.I)
GREETING = re.compile(r"^(dear|hi|hello|hey|good (morning|afternoon|evening)|bonjour|bonsoir|salut|cher|chère|chers|madame|monsieur|sehr geehrte|liebe|lieber|hallo|guten (tag|morgen|abend)|buongiorno|ciao|gentile|estimad[oa]|hola)\b", re.I)
_WORD = re.compile(r"[^\W\d_]+", re.U)


def detect_language(text: str) -> tuple[str | None, float]:
    """(language code or None, share of recognised words). Needs a few clear signals, else None."""
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < 5:
        return None, 0.0
    scores = {lang: sum(1 for w in words if w in sw) for lang, sw in STOPWORDS.items()}
    best, second = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:2]
    if best[1] < 2 or best[1] < second[1] * 1.3 + 0.01:
        return None, 0.0
    return best[0], round(best[1] / len(words), 3)


def _lines(body: str) -> list[str]:
    return [ln.strip() for ln in (body or "").splitlines()]


def greeting_of(body: str, names: list[str]) -> str | None:
    """First line if it looks like a greeting; the recipient's name becomes {name}."""
    for ln in _lines(body):
        if not ln:
            continue
        if len(ln) > 70 or not GREETING.match(ln):
            return None
        out = ln
        for n in sorted({n for n in names if n and len(n) > 1}, key=len, reverse=True):
            out = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)", "{name}", out, flags=re.I)
        return re.sub(r"\{name\}(?:\s+\{name\})+", "{name}", out).strip()          # 'Daniel Stauffacher' -> one {name}
    return None


def closing_and_signature(body: str) -> tuple[str | None, list[str]]:
    """The last closing phrase ('Kind regards,') and the lines after it (her signature)."""
    lines = _lines(body)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] and len(lines[i]) <= 40 and CLOSINGS.match(lines[i]):
            sig = [ln for ln in lines[i + 1:i + 8] if ln]
            return lines[i], sig
    return None, []


def formality_of(texts: list[str], greetings: list[str | None], closings: list[str | None], lang: str | None) -> tuple[str, str | None]:
    """('formal'|'informal'|'neutral', pronoun) from her own words to this person."""
    blob = "\n".join(texts)
    if lang == "fr":
        v = len(re.findall(r"\b(vous|votre|vos)\b", blob, re.I)); t = len(re.findall(r"\b(tu|toi|ton|ta|tes)\b", blob, re.I))
        if v or t:
            return ("formal", "vous") if v >= t else ("informal", "tu")
    if lang == "de":
        f = len(re.findall(r"(?<![.!?]\s)(?<!^)\b(Sie|Ihnen|Ihr|Ihre|Ihren)\b", blob)); i = len(re.findall(r"\b(du|dir|dich|dein|deine)\b", blob))
        if f or i:
            return ("formal", "Sie") if f >= i else ("informal", "du")
    formal = informal = 0
    for g in filter(None, greetings):
        if re.match(r"(dear|sehr geehrte|madame|monsieur|cher (monsieur|madame)|gentile|estimad)", g, re.I) or re.search(r"\b(mr|ms|mrs|dr|prof|ambassador|excellency|madame|monsieur|herr|frau)\b", g, re.I):
            formal += 1
        elif re.match(r"(hi|hey|salut|ciao|hallo|hola)\b", g, re.I):
            informal += 1
    for c in filter(None, closings):
        if re.match(r"(sincerely|yours|salutations distinguées|meilleures salutations|mit freundlichen|cordiali|atentamente)", c, re.I):
            formal += 1
        elif re.match(r"(cheers|thanks|ciao|amicalement|à bientôt|bien à vous|viele gr|saludos)", c, re.I):
            informal += 1
    informal += min(blob.count("!"), 3) // 3
    if formal > informal:
        return "formal", None
    if informal > formal:
        return "informal", None
    return "neutral", None


def build_profile(mine: list[dict], theirs: list[dict], names: list[str]) -> dict:
    """mine/theirs: [{'body': str, 'language': str|None}]. Returns the profile fields."""
    texts = [m["body"] or "" for m in mine]
    langs = Counter(l for l, _ in (detect_language(t) for t in texts) if l)
    if not langs:                                                           # fall back to how THEY write to her
        langs = Counter(l for l, _ in (detect_language(t["body"] or "") for t in theirs) if l)
    lang = langs.most_common(1)[0][0] if langs else None
    greetings = [greeting_of(t, names) for t in texts]
    closings = [closing_and_signature(t)[0] for t in texts]
    gcount, ccount = Counter(g for g in greetings if g), Counter(c for c in closings if c)
    formality, pronoun = formality_of(texts, greetings, closings, lang) if mine else ("neutral", None)
    n = len(mine)
    return {
        "language": lang, "formality": formality, "pronoun": pronoun,
        "greeting": gcount.most_common(1)[0][0] if gcount else None,
        "closing": ccount.most_common(1)[0][0] if ccount else None,
        "avg_words": round(sum(len(t.split()) for t in texts) / n) if n else None,
        "n_mine": n, "n_theirs": len(theirs),
        "confidence": "none" if n == 0 else "low" if n < 3 else "medium" if n < 5 else "high",
    }


def learned_signature(all_mine: list[str]) -> str | None:
    """Her signature block: the most common set of lines after her closing, across all her messages."""
    blocks = Counter("\n".join(sig) for _, sig in (closing_and_signature(t) for t in all_mine) if sig)
    return blocks.most_common(1)[0][0] if blocks else None


def _names_for(conn: sqlite3.Connection, email: str) -> list[str]:
    row = conn.execute("SELECT name, aliases FROM people WHERE email = ?", (email,)).fetchone()
    names: list[str] = []
    if row:
        names += [p for p in re.split(r"[\s,;]+", f"{row['name']} {row['aliases'] or ''}") if p]
    return names


def rebuild_profiles(conn: sqlite3.Connection) -> dict:
    """Learn a profile for everyone with correspondence. Her own edits are never overwritten (only counts refresh)."""
    stats = {"learned": 0, "kept_edits": 0}
    people = [r[0] for r in conn.execute("SELECT DISTINCT person_email FROM correspondence_messages")]
    with conn:
        for email in people:
            rows = conn.execute("SELECT from_me, body, language FROM correspondence_messages WHERE person_email=? ORDER BY sent_at", (email,)).fetchall()
            mine = [dict(r) for r in rows if r["from_me"]]
            theirs = [dict(r) for r in rows if not r["from_me"]]
            names = _names_for(conn, email)
            prof = build_profile(mine, theirs, names)
            prof["n_threads"] = conn.execute("SELECT COUNT(*) FROM correspondence_threads WHERE person_email=?", (email,)).fetchone()[0]
            old = conn.execute("SELECT source FROM style_profiles WHERE person_email=?", (email,)).fetchone()
            if old and old["source"] == "edited":
                conn.execute("UPDATE style_profiles SET n_mine=?, n_theirs=?, n_threads=?, avg_words=?, confidence=? WHERE person_email=?",
                             (prof["n_mine"], prof["n_theirs"], prof["n_threads"], prof["avg_words"], prof["confidence"], email))
                stats["kept_edits"] += 1
                continue
            cols = ", ".join(prof)
            conn.execute(f"INSERT INTO style_profiles (person_email, {cols}, source) VALUES (?,{','.join('?' * len(prof))},'learned') "
                         f"ON CONFLICT (person_email) DO UPDATE SET " + ", ".join(f"{k}=excluded.{k}" for k in prof) + ", source='learned', updated_at=datetime('now')",
                         (email, *prof.values()))
            stats["learned"] += 1
        # her signature (global)
        sig = learned_signature([r[0] for r in conn.execute("SELECT body FROM correspondence_messages WHERE from_me=1")])
        if sig:
            conn.execute("INSERT INTO draft_settings (key, value, source) VALUES ('signature_learned', ?, 'learned') "
                         "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')", (sig,))
        cur = conn.execute("SELECT source FROM draft_settings WHERE key='signature'").fetchone()
        if sig and not (cur and cur["source"] == "edited"):
            conn.execute("INSERT INTO draft_settings (key, value, source) VALUES ('signature', ?, 'learned') "
                         "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')", (sig,))
    return stats
