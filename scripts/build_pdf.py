#!/usr/bin/env python3
"""Build a printable PDF from one docs page, so emails can link to it instead of attaching a file.

    python3 scripts/build_pdf.py publishers/wordpress-plugin.mdx files/mediafuse-wordpress-plugin-guide.pdf

Needs Google Chrome or Chromium. Handles only what our guide pages use: headings, paragraphs, lists,
tables, bold, inline code, links, Tip/Note/Warning callouts and accordions. Re-run it after editing the page
and commit the PDF together with the page.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

SITE = "https://docs.mediafuse.org"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def inline(text, page_url):
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    def link(m):
        label, href = m.group(1), m.group(2)
        if href.startswith("/files/"):
            href = SITE + href
        elif href.startswith("/"):
            href = SITE + href
        elif href.startswith("#"):
            href = page_url + href
        return f'<a href="{href}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)


def convert(body, page_url):
    out, para, lst, table = [], [], None, []

    def flush():
        nonlocal para, lst, table
        if para:
            out.append("<p>" + inline(" ".join(para), page_url) + "</p>")
            para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i, page_url)}</li>" for i in items) + f"</{tag}>")
            lst = None
        if table:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table if not re.match(r"^\|[-\s|]+\|$", r.strip())]
            head = "".join(f"<th>{inline(c, page_url)}</th>" for c in rows[0])
            rest = "".join("<tr>" + "".join(f"<td>{inline(c, page_url)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rest}</tbody></table>")
            table = []

    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        m = re.match(r"^<(Tip|Note|Warning)>$", line)
        if m:
            flush(); out.append(f'<div class="callout {m.group(1).lower()}">'); continue
        if re.match(r"^</(Tip|Note|Warning)>$", line):
            flush(); out.append("</div>"); continue
        if line in ("<AccordionGroup>", "</AccordionGroup>"):
            flush(); continue
        m = re.match(r'^<Accordion title="([^"]+)">$', line)
        if m:
            flush(); out.append(f'<div class="accordion"><h4>{html.escape(m.group(1))}</h4>'); continue
        if line == "</Accordion>":
            flush(); out.append("</div>"); continue
        m = re.match(r"^(#{2,4}) (.+)$", line)
        if m:
            flush(); n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2), page_url)}</h{n}>"); continue
        if line.startswith("|"):
            if para or lst: flush()
            table.append(line); continue
        m = re.match(r"^(\d+)\. (.+)$", line) or re.match(r"^- (.+)$", line)
        if m:
            tag = "ol" if line[0].isdigit() else "ul"
            if para or table: flush()
            if lst and lst[0] != tag: flush()
            if not lst: lst = (tag, [])
            lst[1].append(m.group(m.lastindex)); continue
        if lst:
            lst[1][-1] += " " + line; continue
        para.append(line)
    flush()
    return "\n".join(out)


CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: Inter, 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1f2933; }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #0D9373; padding-bottom: 10px; margin-bottom: 18px; }
header img { height: 30px; }
header .meta { font-size: 8.5pt; color: #6b7280; text-align: right; }
h1 { font-size: 21pt; margin: 0 0 4px; color: #111827; }
.lead { font-size: 11.5pt; color: #4b5563; margin: 0 0 16px; }
h2 { font-size: 14pt; color: #096e56; margin: 22px 0 6px; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14px 0 4px; page-break-after: avoid; }
h4 { font-size: 10.5pt; margin: 0 0 4px; }
code { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 9.5pt; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
a { color: #0D9373; text-decoration: none; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #d1d5db; padding: 5px 7px; text-align: left; vertical-align: top; }
th { background: #ecfdf5; }
ol, ul { padding-left: 20px; margin: 4px 0 8px; }
li { margin: 2px 0; }
.callout { border-left: 4px solid #0D9373; background: #ecfdf5; padding: 6px 12px; margin: 10px 0; border-radius: 4px; page-break-inside: avoid; }
.callout.warning { border-color: #d97706; background: #fffbeb; }
.callout.note { border-color: #2563eb; background: #eff6ff; }
.callout p { margin: 4px 0; }
.accordion { border: 1px solid #e5e7eb; border-radius: 4px; padding: 8px 12px; margin: 8px 0; page-break-inside: avoid; }
footer { margin-top: 24px; border-top: 1px solid #e5e7eb; padding-top: 8px; font-size: 8.5pt; color: #6b7280; }
"""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dest = sys.argv[1], sys.argv[2]
    text = open(os.path.join(ROOT, src), encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    front, body = m.group(1), text[m.end():]
    title = re.search(r'^title: "(.*)"$', front, re.M).group(1)
    desc = re.search(r'^description: "(.*)"$', front, re.M).group(1)
    page_url = SITE + "/" + re.sub(r"\.mdx$", "", src)
    # The online page offers this PDF; inside the PDF, point to the online page instead.
    body = re.sub(r"<Tip>\s*Prefer a file\?.*?</Tip>",
                  f"<Tip>\nOnline version, always up to date: [{page_url.replace('https://', '')}]({page_url})\n</Tip>",
                  body, flags=re.S)

    logo = "file://" + os.path.join(ROOT, "logo/mediafuse/Logo_MediaFuse.svg")
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)} - MediaFuse</title>
<style>{CSS}</style></head><body>
<header><img src="{logo}" alt="MediaFuse"><div class="meta">Publisher guide<br>{date.today():%d %B %Y}</div></header>
<h1>{html.escape(title)} setup guide</h1><p class="lead">{html.escape(desc)}</p>
{convert(body, page_url)}
<footer>MediaFuse publisher documentation: {SITE.replace('https://', '')}</footer>
</body></html>"""

    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if not chrome:
        sys.exit("Chrome or Chromium is needed to print the PDF")
    with tempfile.TemporaryDirectory() as tmp:
        page = os.path.join(tmp, "page.html")
        open(page, "w", encoding="utf-8").write(doc)
        out = os.path.abspath(os.path.join(ROOT, dest))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--allow-file-access-from-files", f"--print-to-pdf={out}", "file://" + page],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(out)


if __name__ == "__main__":
    main()
