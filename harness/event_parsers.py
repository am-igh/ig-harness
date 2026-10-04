"""Parsers that turn event emails and newsletters into structured events. Pure standard library (used by the Mac-side helper and by the importer).
Deterministic rules only; anything they cannot read (no date found, free-form invitations) is left to the local-model step.
Patterns come from the real senders: Club Diplomatique subjects, Luma registration emails, organiser confirmations, the Genève internationale tables."""
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Zurich")
MONTHS = {m: i for i, names in enumerate([
    ("january", "jan", "janvier", "januar"), ("february", "feb", "février", "fevrier", "februar"), ("march", "mar", "mars", "märz", "maerz"), ("april", "apr", "avril"),
    ("may", "mai"), ("june", "jun", "juin", "juni"), ("july", "jul", "juillet", "juli"), ("august", "aug", "août", "aout"), ("september", "sep", "sept", "septembre"),
    ("october", "oct", "octobre", "oktober", "okt"), ("november", "nov", "novembre"), ("december", "dec", "décembre", "decembre", "dezember", "dez")], 1) for m in names}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))


def _month(name: str) -> int | None:
    return MONTHS.get(name.lower().strip("."))


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def at_geneva(day_iso: str, hhmm: str) -> str:
    """Local Geneva time -> ISO with the right offset for that date (summer or winter time)."""
    h, m = [int(x) for x in re.split(r"[:h]", hhmm)[:2]]
    d = date.fromisoformat(day_iso)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ).isoformat()


# ------------------------------------------------------------------ Club Diplomatique de Genève (subject lines)
_CLUB = re.compile(r"^\W*(?P<kind>Invitation|Reminder|Information|Rappel|Einladung)\s*\|\s*(?P<title>.+?),\s*(?P<day>\d{1,2})(?:st|nd|rd|th|er)?\s+(?P<month>[A-Za-zéûôäö]+)\s+(?P<year>\d{4})"
                   r"(?:\s+(?:at|from|à|um|ab)\s+(?P<time>\d{1,2}[:h]\d{2}))?(?:\s*,\s*(?P<venue>.+))?\s*$", re.I)


def parse_club_subject(subject: str) -> dict | None:
    m = _CLUB.match((subject or "").strip())
    mon = _month(m.group("month")) if m else None
    if not m or not mon:
        return None
    day = _iso(int(m.group("year")), mon, int(m.group("day")))
    if not day:
        return None
    t = m.group("time")
    return {"kind": m.group("kind").lower(), "title": m.group("title").strip(), "start": at_geneva(day, t) if t else day, "all_day": t is None,
            "venue": (m.group("venue") or "").strip() or None, "organizer": "Club Diplomatique de Genève"}


# ------------------------------------------------------------------ Luma registration emails (subject + the start of the body)
_LUMA_SUBJ = re.compile(r"^(?:Registration|Your registration)\s+(?P<what>approved|confirmed|pending approval)\s+for\s+(?P<title>.+)$", re.I)
_LUMA_WHEN = re.compile(r"(?:[A-Z]{3}\s+\d{1,2}\s+)?(?:[A-Z][a-z]+day,\s+)?(?P<month>[A-Z][a-z]+)\s+(?P<d>\d{1,2})\s+(?P<t1>\d{1,2}:\d{2}\s*[AP]M)"
                        r"(?:\s*-\s*(?:(?P<mon2>[A-Z][a-z]+)\s+(?P<d2>\d{1,2}),\s+)?(?P<t2>\d{1,2}:\d{2}\s*[AP]M))?\s*GMT(?P<off>[+-]\d{1,2})(?::?(?P<offm>\d{2}))?\s*(?P<rest>.*)")


def _t24(s: str) -> str:
    return datetime.strptime(re.sub(r"\s+", " ", s.strip().upper()), "%I:%M %p").strftime("%H:%M")


def parse_luma(subject: str, snippet: str, sent_iso: str) -> dict | None:
    s = _LUMA_SUBJ.match((subject or "").strip())
    if not s:
        m = re.match(r"^(?:You have registered for|You'?re registered for)\s+(?P<title>.+)$", (subject or "").strip(), re.I)
        if not m:
            return None
        what, title = "confirmed", m.group("title")
    else:
        what, title = s.group("what").lower(), s.group("title")
    w = _LUMA_WHEN.search(re.sub(r"\s+", " ", snippet or ""))
    if not w:
        return None
    mon = _month(w.group("month"))
    if not mon:
        return None
    sent = date.fromisoformat(sent_iso[:10])
    y = sent.year
    day = _iso(y, mon, int(w.group("d")))
    if day and date.fromisoformat(day) < sent - timedelta(days=45):
        day = _iso(y + 1, mon, int(w.group("d")))                                 # an event in January for a December email
    if not day:
        return None
    off = int(w.group("off")); offm = int(w.group("offm") or 0)
    from datetime import timezone
    tz = timezone(timedelta(hours=off, minutes=offm if off >= 0 else -offm))
    def stamp(day_iso, t12):
        d = date.fromisoformat(day_iso); hh, mm = [int(x) for x in _t24(t12).split(":")]
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz).isoformat()
    end_day = day
    if w.group("mon2"):
        m2 = _month(w.group("mon2"))
        end_day = _iso(date.fromisoformat(day).year + (1 if m2 and m2 < mon else 0), m2 or mon, int(w.group("d2"))) or day
    rest = (w.group("rest") or "").split("↗")[0].split("Event Page")[0].strip(" ·-")
    return {"what": what, "title": title.strip(), "start": stamp(day, w.group("t1")), "end": stamp(end_day, w.group("t2")) if w.group("t2") else None, "all_day": False,
            "venue": rest[:120] or None, "online": bool(re.match(r"(?i)^(zoom|online|virtual|google meet|teams)", rest))}


# ------------------------------------------------------------------ organiser confirmations ("Registration Confirmed - Summit 2026")
_REG_SUBJ = re.compile(r"(registration|registered|inscription).{0,30}(confirm|approved)|(confirm).{0,25}(registration|inscription)|you['’]?re confirmed|you are confirmed|thank you for registering", re.I)
_NOT_EVENT_SUBJ = re.compile(r"\b(booking|flight|purchase|order|payment|invoice|subscription|hotel|reservation of)\b", re.I)


def is_registration_confirmation(subject: str) -> bool:
    return bool(_REG_SUBJ.search(subject or "")) and not _NOT_EVENT_SUBJ.search(subject or "")


def event_title_from_registration(subject: str) -> str | None:
    s = re.sub(r"(?i)^(re|fwd?|aw|tr):\s*", "", (subject or "").strip())
    parts = [p.strip() for p in re.split(r"\s+[-–—|]\s+|:\s+", s) if p.strip()]
    keep = [p for p in parts if not re.search(r"(?i)registration|confirm|inscription|important|pre-arrival|information|badge|thank you", p)]
    if not keep:
        m = re.search(r"(?i)(?:for|to)\s+(.+)$", s)
        return m.group(1).strip() if m else None
    return " - ".join(keep)[:160]


def extract_date_range(text: str, hint: date) -> tuple[str, str | None] | None:
    """First date or date range in free text: '14-15 October 2026', '4 May to Friday, 8 May 2026', 'October 14-15, 2026', '14 October 2026'."""
    t = re.sub(r"\s+", " ", text or "")
    wd = r"(?:(?:mon|tues?|wednes|thurs?|fri|satur|sun)day,?\s+)?"
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|to|au|bis)\s*{wd}(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(\d{{4}})", t, re.I)
    if m and _month(m.group(3)):
        mo = _month(m.group(3)); y = int(m.group(4))
        return _iso(y, mo, int(m.group(1))) or "", _iso(y, mo, int(m.group(2))) if _iso(y, mo, int(m.group(1))) else None
    m = re.search(rf"\b{wd}(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?\s+(?:to|-|–|au|bis)\s+{wd}(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(\d{{4}})", t, re.I)
    if m and _month(m.group(2)) and _month(m.group(4)):
        y = int(m.group(5))
        a, b = _iso(y, _month(m.group(2)), int(m.group(1))), _iso(y, _month(m.group(4)), int(m.group(3)))
        return (a, b) if a and b else None
    m = re.search(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:\s*(?:-|–)\s*(\d{{1,2}}))?,?\s+(\d{{4}})", t, re.I)
    if m and _month(m.group(1)):
        mo, y = _month(m.group(1)), int(m.group(4))
        a = _iso(y, mo, int(m.group(2)))
        return (a, _iso(y, mo, int(m.group(3))) if m.group(3) else None) if a else None
    m = re.search(rf"\b{wd}(\d{{1,2}})(?:st|nd|rd|th|er)?\s+({_MON})\.?,?\s+(\d{{4}})", t, re.I)
    if m and _month(m.group(2)):
        a = _iso(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
        return (a, None) if a else None
    return None


def parse_registration(subject: str, snippet: str, sent_iso: str) -> dict | None:
    if not is_registration_confirmation(subject):
        return None
    title = event_title_from_registration(subject)
    rng = extract_date_range(f"{subject}. {snippet}", date.fromisoformat(sent_iso[:10]))
    if not title or not rng or not rng[0]:
        return None
    start, end = rng
    return {"title": title, "start": start, "end": (date.fromisoformat(end) + timedelta(days=1)).isoformat() if end else None, "all_day": True,   # all-day ends are exclusive
            "venue": None}


# ------------------------------------------------------------------ Genève internationale weekly newsletter (HTML tables)
class _GITables(HTMLParser):
    """Rows: organizer logo (img alt), title link, start and end date (dd.mm.yyyy), location, link. Themes are the text just before each header row."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.theme, self.cur, self.last_text, self.in_a, self.in_th, self.in_span, self.skip = [], None, None, "", False, False, False, 0
        self.started, self.last_any = False, ""             # events only count after the first "Organizer" header (the page's own logos come before)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("tr", "td", "tbody"):
            self.in_th = False                              # the real newsletter never closes its <th> cells
        if tag == "th":
            self.in_th = True
        if tag == "img" and self.started and re.search(r"(?i)\blogo\b", a.get("alt") or "") and (a.get("alt") or "").strip().lower() != "location":
            if self.cur:
                self._close()
            self.cur = {"theme": self.theme, "organizer": re.sub(r"(?i)\s*\blogo\b\s*", " ", a["alt"]).strip(" _-"), "title": "", "dates": [], "location": "", "url": None, "_loc": False}
        elif tag == "img" and self.cur is not None and (a.get("alt") or "").lower() == "location":
            self.cur["_loc"] = True
        if tag == "a" and self.cur is not None and a.get("href"):
            self.in_a = True
            if self.cur["url"] is None:
                self.cur["url"] = a["href"].strip().rstrip('"')
        if tag == "span" and self.cur is not None and self.cur["_loc"] and not self.cur["location"]:
            self.in_span = True

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag in ("th", "thead", "tr"):
            self.in_th = False
        if tag == "a":
            self.in_a = False
        if tag == "span":
            self.in_span = False

    def handle_data(self, data):
        if self.skip:
            return
        t = re.sub(r"\s+", " ", data).strip()
        if not t:
            return
        if self.in_th:
            if t.lower() == "organizer":
                if self.cur:
                    self._close()
                self.started = True
                self.theme = self.last_any or self.theme              # the text just before the header row names the section
            return
        self.last_any = t
        if self.cur is None:
            self.last_text = t
            return
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", t):
            self.cur["dates"].append(t)
        elif self.in_a and not self.cur["title"]:
            self.cur["title"] = t
        elif self.in_span and not self.cur["location"]:
            self.cur["location"] = t
            self.in_span = False
        elif not self.cur["dates"] and not self.cur["title"]:
            pass
        else:
            self.last_text = t

    def _close(self):
        c = self.cur
        self.cur = None
        if c and c["title"] and c["dates"]:
            d = [datetime.strptime(x, "%d.%m.%Y").date().isoformat() for x in c["dates"][:2]]
            self.rows.append({"theme": c["theme"], "organizer": c["organizer"], "title": c["title"], "start": d[0], "end": d[-1], "location": c["location"] or None, "url": c["url"]})

    def close(self):
        super().close()
        if self.cur:
            self._close()


def parse_geneve_int(html: str) -> list[dict]:
    p = _GITables()
    p.feed(html or "")
    p.close()
    seen, out = set(), []
    for r in p.rows:
        k = (r["title"], r["start"])
        if k not in seen:
            seen.add(k); out.append(r)
    return out


# ------------------------------------------------------------------ public web pages (fetched by tools/events_helper.py; S0 data)
def _text(fragment: str) -> str:
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"(?s)<[^>]+>", " ", fragment or ""))).strip()


def _organizer(alt: str | None) -> str | None:
    """'Logo WMO', 'Logo-ITU', 'GESDA_Logo.png', 'UN HRC' -> the organizer's name."""
    t = re.sub(r"(?i)\.(png|jpe?g|svg|gif)$", "", (alt or "").strip())
    t = re.sub(r"(?i)[\s_\-]*\blogo\b[\s_\-]*", " ", t.replace("_", " ").replace("-", " ") if re.search(r"(?i)logo", t) else t)
    return re.sub(r"\s+", " ", t).strip() or None


def parse_geneve_int_web(page_html: str) -> list[dict]:
    """The calendar page of geneve-int.ch: one table row per event (organizer logo alt, title, start and end <time datetime>, address, link)."""
    out = []
    for row in re.findall(r"(?is)<tr\b.*?</tr>", page_html or ""):
        title = re.search(r'(?is)class="event-title"[^>]*>(.*?)</div>', row)
        times = re.findall(r'(?is)<time[^>]*datetime="(\d{4}-\d{2}-\d{2})', row)
        if not title or not times:
            continue
        org = re.search(r'(?is)<img[^>]*\balt="([^"]*)"', row)
        addr = re.search(r'(?is)views-field-event-address[^>]*>(.*?)</td>', row)
        link = re.search(r'(?is)views-field-field-link[^>]*>\s*<a[^>]*href="([^"]+)"', row)
        out.append({"title": _text(title.group(1)), "start": times[0], "end": times[-1], "organizer": _organizer(_text(org.group(1))) if org else None,
                    "venue": _text(addr.group(1)) if addr else None, "url": _text(link.group(1)) if link else None})
    return out


def parse_club_events(page_html: str) -> list[dict]:
    """clubdiplomatique.ch/evenements: one <article> per event with the title, a French date line ('lundi 12 octobre 2026') and the venue."""
    out = []
    for art in re.findall(r"(?is)<article\b.*?</article>", page_html or ""):
        a = re.search(r'(?is)<h\d[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', art)
        paras = [_text(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", art)]
        rng = next((extract_date_range(p, date.today()) for p in paras if re.search(r"\d{4}", p)), None)
        if not a or not rng or not rng[0]:
            continue
        venue = next((p for p in paras if p and not re.search(r"\d{4}", p) and p.upper() not in ("ANG", "FR", "ANG/FR", "FR/ANG", "EN")), None)
        start, end = rng
        out.append({"title": _text(a.group(2)), "start": start, "end": end, "organizer": "Club Diplomatique de Genève", "venue": venue, "url": a.group(1)})
    return out


def parse_unog(page_html: str, year: int) -> list[dict]:
    """The UN Geneva calendar of major meetings: rows of (body and session, start 'd-Mon', end 'd-Mon'); the year is the calendar's."""
    out = []
    for row in re.findall(r"(?is)<tr\b.*?</tr>", page_html or ""):
        cells = re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", row)
        if len(cells) < 3:
            continue
        def dm(s):
            m = re.search(r"(\d{1,2})\s*[-\s]?\s*([A-Za-z]{3,9})", _text(s))
            mon = _month(m.group(2)) if m else None
            return _iso(year, mon, int(m.group(1))) if m and mon else None
        a, b = dm(cells[1]), dm(cells[2])
        strong = re.search(r"(?is)<strong[^>]*>(.*?)</strong>|<b>(.*?)</b>", cells[0])
        body = _text((strong.group(1) or strong.group(2)) if strong else cells[0].split("<")[0])
        link = re.search(r'(?is)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', cells[0])
        if not body or not a:
            continue
        session = _text(link.group(2)) if link else ""
        out.append({"title": f"{body} – {session}" if session and session not in body else body, "start": a, "end": b if b and b >= a else a, "organizer": "UN Geneva",
                    "venue": "Palais des Nations", "url": _text(link.group(1)) if link else None})
    return out
