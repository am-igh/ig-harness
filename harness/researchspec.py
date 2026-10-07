"""Rules for web research, shared by the API and the Mac-side research helper (pure standard library).
 - screen(): what may leave the Mac as a search query. IBANs, AVS numbers and credentials are refused outright; things that look confidential (a person's full name from People,
   an email address, an amount, bank or salary words) need her confirmation first.
 - public_https_url(): a page may be fetched only if it is https on the normal port and every address its host resolves to is a public one (no localhost, private networks,
   Tailscale or link-local addresses), so a search result can never point the helper at her own machine or network.
 - extract_text(): the readable text of a page, without scripts, menus or forms."""
import hashlib
import ipaddress
import re
import urllib.parse
from html.parser import HTMLParser

MAX_QUERY = 300
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{3,5}){3,8}\b")
_AVS = re.compile(r"\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b")
_CREDENTIAL = re.compile(r"(\b(password|passwort|mot de passe|passphrase|api[ _-]?key|secret|token)\b\s*[:=]|sk-ant-|sk-[A-Za-z0-9]{20,}|BEGIN (?:RSA |EC )?PRIVATE KEY|bearer\s+[A-Za-z0-9._-]{20,})", re.I)
_EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
_MONEY = re.compile(r"(\b(CHF|EUR|USD|GBP)\s?\d[\d'’., ]*|\d[\d'’., ]*\s?(CHF|EUR|USD|GBP|€|\$)|[€$£]\s?\d)", re.I)
_WORDS = re.compile(r"\b(salary|salaries|salaire|payroll|payslip|bank statement|relev[ée] de compte|invoice|facture|contract|contrat|diagnos\w*|medical|passport)\b", re.I)


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def _norm(t: str) -> str:
    import unicodedata
    return " " + re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()).strip() + " "


def screen(query: str, known_names: list[str] | None = None) -> dict:
    """{'ok': bool, 'blocked': [reasons], 'warnings': [reasons], 'query': cleaned}. Blocked means never sent; warnings need her confirmation."""
    q = " ".join((query or "").split())
    out = {"ok": True, "blocked": [], "warnings": [], "query": q}
    if not q:
        out["blocked"].append("The question is empty.")
    if len(q) > MAX_QUERY:
        out["blocked"].append(f"The question is too long for a search (max {MAX_QUERY} characters).")
    if _IBAN.search(q):
        out["blocked"].append("It contains what looks like an IBAN.")
    if _AVS.search(q):
        out["blocked"].append("It contains what looks like an AVS number.")
    if _CREDENTIAL.search(q):
        out["blocked"].append("It contains what looks like a password, key or token.")
    if _EMAIL.search(q):
        out["warnings"].append("It contains an email address.")
    if _MONEY.search(q):
        out["warnings"].append("It contains an amount of money.")
    if _WORDS.search(q):
        out["warnings"].append("It mentions something that is often confidential (money, contracts, health or identity documents).")
    nq = _norm(q)
    for n in known_names or []:
        words = _norm(n).split()
        if len(words) >= 2 and all(f" {w} " in nq for w in words):
            out["warnings"].append(f"It contains the name of someone in your People list ({n}).")
    out["ok"] = not out["blocked"]
    return out


def public_https_url(url: str, resolver) -> str:
    """The url if it is safe to fetch; raises ValueError (with the reason) otherwise. `resolver` is the DNS lookup (socket.getaddrinfo), supplied by the Mac-side helper:
    this module never touches the network."""
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "https":
        raise ValueError("only https pages are fetched")
    if u.username or u.password or u.port not in (None, 443):
        raise ValueError("this address form is not allowed")
    host = (u.hostname or "").strip(".").lower()
    if not host or host in ("localhost",) or host.endswith((".local", ".internal", ".localhost", ".lan", ".home.arpa")):
        raise ValueError("this host is not a public website")
    try:
        infos = resolver(host, 443)
    except OSError:
        raise ValueError("the host could not be found")
    addrs = {i[4][0] for i in infos}
    if not addrs:
        raise ValueError("the host could not be found")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError("this host points to a private or local address")
    return url


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "iframe", "template"}
    BLOCK = {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4", "tr", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def extract_text(html: str, limit: int = 6000) -> tuple[str, str]:
    """(title, readable text) of a page; short fragments (menus, buttons) are dropped."""
    p = _Text()
    try:
        p.feed(html)
    except Exception:
        pass
    lines = [" ".join(x.split()) for x in "".join(p.parts).split("\n")]
    text = "\n".join(x for x in lines if len(x) >= 40)
    return " ".join(p.title.split())[:200], text[:limit]
