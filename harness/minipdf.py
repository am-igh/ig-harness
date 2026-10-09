"""A tiny PDF writer for the demo's fictitious contracts: A4 pages of wrapped text (Helvetica and Helvetica-Bold), a banner on every page and page numbers. Pure standard library, ASCII text only.
It exists so the demo can show and download real PDF files without any extra software."""
import zlib

W, H, MARGIN = 595.0, 842.0, 62.0
# Helvetica widths in 1/1000 em for ASCII 32..126
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015,
      667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333,
      556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]


def _clean(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-").replace(" ", " ").encode("ascii", "replace").decode()


def _width(text: str, size: float, bold: bool = False) -> float:
    w = sum(_W[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text) * size / 1000.0
    return w * (1.06 if bold else 1.0)


def _wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    lines, cur = [], ""
    for word in _clean(text).split():
        trial = (cur + " " + word).strip()
        if cur and _width(trial, size, bold) > width * 0.97:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class _Page:
    def __init__(self):
        self.ops: list[str] = []
        self.y = H - MARGIN - 18


def build_pdf(title: str, blocks: list[tuple], banner: str = "FICTITIOUS DOCUMENT FOR DEMONSTRATION - NOT A REAL CONTRACT") -> bytes:
    """blocks: ('h1', text) ('h2', text) ('p', text) ('li', text) ('kv', [(key, value), ...]) ('sp', points) ('sig', [(name, role), ...])"""
    pages: list[_Page] = [_Page()]
    inner = W - 2 * MARGIN

    def room(p: _Page, need: float) -> _Page:
        if p.y - need < MARGIN + 24:
            pages.append(_Page())
            return pages[-1]
        return p

    def text(p: _Page, s: str, x: float, size: float, bold: bool = False, gray: float = 0.0) -> None:
        p.ops.append(f"BT /{'F2' if bold else 'F1'} {size} Tf {gray} g {x:.1f} {p.y:.1f} Td ({_esc(s)}) Tj ET")

    for kind, val in blocks:
        p = pages[-1]
        if kind in ("h1", "h2"):
            size, bold, gap = (17, True, 10) if kind == "h1" else (11.5, True, 6)
            lines = _wrap(val, size, inner, True)
            p = room(p, len(lines) * (size + 4) + gap + 10)
            p.y -= 6 if kind == "h2" else 0
            for ln in lines:
                text(p, ln, MARGIN, size, True, 0.1)
                p.y -= size + 4
            p.y -= gap
        elif kind in ("p", "li"):
            indent = 16 if kind == "li" else 0
            lines = _wrap(val, 10, inner - indent)
            p = room(p, min(len(lines), 3) * 14 + 4)
            for i, ln in enumerate(lines):
                p = room(p, 14)
                if kind == "li" and i == 0:
                    text(p, "-", MARGIN + 4, 10)
                text(p, ln, MARGIN + indent, 10)
                p.y -= 13.5
            p.y -= 4
        elif kind == "kv":
            for k, v in val:
                lines = _wrap(v, 10, inner - 150)
                p = room(p, len(lines) * 14)
                text(p, _clean(k), MARGIN, 10, True, 0.25)
                for ln in lines or [""]:
                    text(p, ln, MARGIN + 150, 10)
                    p.y -= 13.5
            p.y -= 6
        elif kind == "sp":
            p.y -= val
        elif kind == "sig":
            p = room(p, 90)
            x = MARGIN
            for name, role in val:
                p.ops.append(f"0.6 G {x:.1f} {p.y - 36:.1f} m {x + 190:.1f} {p.y - 36:.1f} l S")
                text(p, "Signed (fictitious)", x, 8, False, 0.45)
                p.y -= 48
                text(p, _clean(name), x, 10, True)
                p.y -= 12
                text(p, _clean(role), x, 9, False, 0.3)
                p.y += 60
                x += 230
            p.y -= 75
    objs: list[bytes] = []
    n = len(pages)
    # objects: 1 catalog, 2 pages, 3 F1, 4 F2, then per page: page obj, content obj
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, p in enumerate(pages):
        head = [f"BT /F2 8 Tf 0.55 g {MARGIN:.1f} {H - 34:.1f} Td ({_esc(_clean(banner))}) Tj ET", f"0.8 G {MARGIN:.1f} {H - 42:.1f} m {W - MARGIN:.1f} {H - 42:.1f} l S",
                f"BT /F1 8 Tf 0.5 g {MARGIN:.1f} 34 Td ({_esc(_clean(title)[:90])}) Tj ET", f"BT /F1 8 Tf 0.5 g {W - MARGIN - 50:.1f} 34 Td (Page {i + 1} of {n}) Tj ET"]
        stream = zlib.compress("\n".join(head + p.ops).encode("latin-1"))
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info << /Title ({_esc(_clean(title))}) /Producer (IG Harness demo) >> >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
