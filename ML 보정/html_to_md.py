# 최종보고서.html을 마크다운으로 변환한다. 내용(표·숫자·문장)은 그대로 두고 CSS, 링크 목차, SVG 그래프만 뺀다.
import re
import sys
from bs4 import BeautifulSoup, NavigableString, Tag

SRC = "B/최종보고서.html"
DST = "B/최종보고서.md"
soup = BeautifulSoup(open(SRC, encoding="utf-8").read(), "lxml")
paper = soup.find("article", class_="paper")


def esc(t):
    t = t.replace("\\", "\\\\").replace("*", "\\*").replace("<", "&lt;").replace(">", "&gt;")
    return t


def inline(node):
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            out.append(esc(re.sub(r"\s+", " ", str(c))))
        elif isinstance(c, Tag):
            name = c.name
            if name in ("b", "strong"):
                s = inline(c).strip()
                out.append(f"**{s}**" if s else "")
            elif name == "code":
                s = c.get_text()
                out.append(f"`{s}`")
            elif name == "br":
                out.append("  \n")
            elif name == "sub":
                out.append(f"<sub>{c.get_text()}</sub>")
            elif name == "span" and "tag" in (c.get("class") or []):
                out.append(f"[{c.get_text().strip()}]")
            elif name in ("ul", "ol"):
                continue
            else:
                out.append(inline(c))
    return re.sub(r"[ ]{2,}(?!\n)", " ", "".join(out))


def cell_text(c):
    s = inline(c).strip().replace("\n", " ").replace("|", "\\|")
    return s


def table_md(t):
    cap = t.find("caption")
    rows = []
    for tr in t.find_all("tr"):
        cells = []
        for td in tr.find_all(["th", "td"]):
            txt = cell_text(td)
            cells.append(txt)
            for _ in range(int(td.get("colspan", 1)) - 1):
                cells.append("")
        rows.append(cells)
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    head, body = rows[0], rows[1:]
    lines = []
    if cap:
        lines.append(f"**{cap.get_text().strip()}**\n")
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + "|".join(["---"] * n) + "|")
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def list_md(lst, indent=0):
    lines = []
    ordered = lst.name == "ol"
    i = 1
    for li in lst.find_all("li", recursive=False):
        mark = "-" if (not ordered or inline(li).strip().startswith(("\\[", "[")) or re.match(r"[A-Z][a-z]+, [A-Z]", inline(li).strip()) or inline(li).strip().startswith("KKBox's")) else f"{i}."
        text = inline(li).strip()
        lines.append("  " * indent + f"{mark} {text}")
        for sub in li.find_all(["ul", "ol"], recursive=False):
            lines.append(list_md(sub, indent + 1))
        i += 1
    return "\n".join(lines)


def quote(md):
    return "\n".join(("> " + l) if l.strip() else ">" for l in md.split("\n"))


def block(el):
    if isinstance(el, NavigableString):
        return ""
    name, cls = el.name, el.get("class") or []
    if name == "header":
        title = el.find("h1")
        h1 = title.get_text(" ", strip=True) if title else ""
        kicker = el.find(class_="kicker")
        sub = el.find(class_="sub")
        meta = el.find(class_="meta")
        parts = [f"# {h1}"]
        if kicker:
            parts.append(f"*{kicker.get_text(strip=True)}*")
        if sub:
            parts.append(sub.get_text(strip=True))
        if meta:
            parts.append("\n".join("- **" + d.find("b").get_text(strip=True) + "**: " + re.sub(r"\s+", " ", d.get_text(" ", strip=True))[len(d.find("b").get_text(strip=True)):].strip() for d in meta.find_all("div", recursive=False)))
        return "\n\n".join(parts)
    if name == "section" and "note-box" in cls:
        t = el.find(class_="t")
        ps = [inline(p).strip() for p in el.find_all("p")]
        return quote(f"**{t.get_text(strip=True)}**\n\n" + "\n\n".join(ps))
    if name == "nav":
        items = [li.get_text(strip=True) for li in el.find_all("li")]
        return "## 목차\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    if name in ("h2", "h3", "h4"):
        return "#" * int(name[1]) + " " + el.get_text(" ", strip=True)
    if name == "p":
        if "lead" in cls:
            return quote(inline(el).strip())
        return inline(el).strip()
    if name in ("ul", "ol"):
        return list_md(el)
    if name == "table":
        return table_md(el)
    if name == "div":
        if "tw" in cls:
            return "\n\n".join(table_md(t) for t in el.find_all("table"))
        if "callout" in cls:
            return quote("\n\n".join(x for x in (block(c) for c in el.children) if x))
        if "kpis" in cls:
            rows = []
            for k in el.find_all(class_="kpi"):
                rows.append((k.find(class_="l").get_text(strip=True), k.find(class_="v").get_text(strip=True), k.find(class_="d").get_text(" ", strip=True)))
            return "| 지표 | 값 | 비고 |\n|---|---|---|\n" + "\n".join(f"| {a} | **{b}** | {c.replace('|', chr(92) + '|')} |" for a, b, c in rows)
        if "flow" in cls:
            steps = []
            for s in el.find_all(class_="step"):
                b = s.find("b")
                head = b.get_text(strip=True) if b else ""
                rest = s.get_text(" ", strip=True)[len(head):].strip() if b else s.get_text(" ", strip=True)
                steps.append(f"- **{head}** {rest}")
            return "\n".join(steps)
        if "split" in cls:
            return "`" + " | ".join(d.get_text(strip=True) for d in el.find_all("div")) + "`  (왼쪽이 앞 구간, 오른쪽이 뒤 구간)"
        if "fig" in cls:
            cap = el.find(class_="cap")
            return quote(f"{cap.get_text(strip=True)}\n\n(그래프는 `B/최종보고서.html`에서 볼 수 있습니다.)")
    if name == "footer":
        return "---\n\n" + inline(el).strip()
    return ""


parts = []
for child in paper.children:
    md = block(child)
    if md.strip():
        parts.append(md.strip())
# 부록 G(분석 진행 과정)는 마크다운으로 직접 쓴 파일을 맺음말(footer) 앞에 붙인다.
extra = open("B/_추가_분석진행과정.md", encoding="utf-8").read().strip()
if parts and parts[-1].startswith("---"):
    parts.insert(len(parts) - 1, extra)
else:
    parts.append(extra)
out = "\n\n".join(parts) + "\n"
out = re.sub(r"\n{3,}", "\n\n", out)
open(DST, "w", encoding="utf-8").write(out)
print("saved", DST, len(out), "자,", out.count("\n|---"), "개 표")
