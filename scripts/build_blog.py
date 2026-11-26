"""Build the blog: blog/*.md -> blog/<slug>.html, blog/index.html, and the homepage nav link.

Each note starts with a front-matter block:

    ---
    title: My title
    date: 2026-11-26
    summary: One sentence shown in lists.
    tags: vLLM, Inference
    lang: zh            # zh or en
    draft: true         # drafts are skipped unless --drafts is passed
    ---

Usage: python3 scripts/build_blog.py [--drafts]
"""

from datetime import date
from html import escape
import hashlib
import math
from pathlib import Path
import re
import sys

import markdown

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "blog"
HLJS = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0"


def asset_version(name):
    return hashlib.sha1((ROOT / "assets" / name).read_bytes()).hexdigest()[:10]


def parse(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise ValueError(f"{path.name}: missing front matter")
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.split("#", 1)[0].strip()
    for key in ("title", "date", "summary"):
        if not meta.get(key):
            raise ValueError(f"{path.name}: front matter needs '{key}'")
    body = text[match.end():]
    return {
        "slug": path.stem,
        "title": meta["title"],
        "date": date.fromisoformat(meta["date"]),
        "summary": meta["summary"],
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "lang": "zh" if meta.get("lang", "en") == "zh" else "en",
        "draft": meta.get("draft", "false").lower() == "true",
        "body": body,
    }


def reading_minutes(note):
    plain = re.sub(r"```.*?```", "", note["body"], flags=re.S)
    cjk = len(re.findall(r"[一-鿿]", plain))
    words = len(re.findall(r"[A-Za-z0-9_]+", plain))
    return max(1, math.ceil(cjk / 400 + words / 220))


def tags_html(tags):
    return "".join(f'<span class="note-tag">{escape(t)}</span>' for t in tags)


def lang_badge(note):
    return '<span class="note-lang">中文</span>' if note["lang"] == "zh" else ""


def page(title, description, body, lang, prefix, css_v, extra_head="", notes_current=""):
    return f"""<!doctype html>
<html lang="{'zh-CN' if lang == 'zh' else 'en'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(description, quote=True)}">
  <title>{escape(title)}</title>
  <link rel="icon" href="{prefix}assets/favicon-32.png" type="image/png" sizes="32x32">
  <link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="{prefix}assets/apple-touch-icon.png">
  <link rel="stylesheet" href="{prefix}assets/style.css?v={css_v}">{extra_head}
</head>
<body class="note-page">
  <header class="topbar">
    <div class="topbar-inner">
      <a class="brand" href="{prefix}index.html"><img class="brand-mark" src="{prefix}assets/favicon.svg" alt="" width="26" height="26">Xinyu Tan</a>
      <nav aria-label="Main navigation">
        <a href="{prefix}index.html#about">About</a>
        <a href="{prefix}index.html#news">News</a>
        <a href="{prefix}index.html#experience">Experience</a>
        <a href="{prefix}index.html#publications">Publications</a>
        <a href="{prefix}index.html#awards">Awards</a>
        <a href="{prefix}blog/index.html"{notes_current}>Blog</a>
      </nav>
    </div>
  </header>
{body}
  <footer class="note-footer"><a href="{prefix}index.html">← Xinyu Tan</a><span>© Xinyu Tan</span></footer>
</body>
</html>
"""


def note_page(note, css_v):
    md = markdown.Markdown(extensions=["fenced_code", "tables", "toc", "sane_lists"],
                           extension_configs={"toc": {"permalink": "#", "permalink_title": ""}})
    content = md.convert(note["body"])
    hl = (f'\n  <link rel="stylesheet" href="{HLJS}/styles/github.min.css" media="(prefers-color-scheme: light)">'
          f'\n  <link rel="stylesheet" href="{HLJS}/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">'
          f'\n  <script defer src="{HLJS}/highlight.min.js" onload="hljs.highlightAll()"></script>')
    draft = '<p class="note-draft">DRAFT · 草稿，未发布</p>' if note["draft"] else ""
    body = f"""  <main class="article">
    <p class="article-back"><a href="index.html">← Blog</a></p>
    {draft}
    <h1>{escape(note['title'])}</h1>
    <p class="article-meta"><time datetime="{note['date'].isoformat()}">{note['date'].isoformat()}</time><span>{reading_minutes(note)} min</span>{tags_html(note['tags'])}</p>
    <div class="article-body">
{content}
    </div>
  </main>"""
    return page(f"{note['title']} · Xinyu Tan", note["summary"], body, note["lang"], "../", css_v, hl,
                notes_current=' aria-current="page"')


def list_items(notes, href_prefix):
    return "\n".join(
        f'<li><time>{n["date"].isoformat()}</time><div><a class="note-title" href="{href_prefix}{n["slug"]}.html">'
        f'{escape(n["title"])}</a>{lang_badge(n)}<p class="note-summary">{escape(n["summary"])}</p>'
        f'<p class="note-tags">{tags_html(n["tags"])}</p></div></li>'
        for n in notes
    )


def index_page(notes, css_v):
    body = f"""  <main class="article">
    <h1>Blog</h1>
    <p class="article-meta">Lessons from training, serving and evaluating LLMs. 实习中踩过的坑与工程经验。<span>{len(notes)} {'post' if len(notes) == 1 else 'posts'}</span></p>
    <ul class="notes-list">
{list_items(notes, '')}
    </ul>
  </main>"""
    return page("Blog · Xinyu Tan", "Blog posts by Xinyu Tan.", body, "en", "../", css_v,
                notes_current=' aria-current="page"')


def replace_block(html, key, content):
    start, end = f"<!-- {key}:start -->", f"<!-- {key}:end -->"
    before, found, tail = html.partition(start)
    _, closing, after = tail.partition(end)
    if not found or not closing:
        raise ValueError(f"Missing HTML markers for {key}")
    return f"{before}{start}\n{content}\n{end}{after}"


def main():
    include_drafts = "--drafts" in sys.argv[1:]
    notes = [parse(p) for p in sorted(NOTES.glob("*.md")) if p.name.lower() != "readme.md"]
    shown = sorted((n for n in notes if include_drafts or not n["draft"]), key=lambda n: n["date"], reverse=True)
    css_v = asset_version("style.css")

    keep = {"index.html"}
    for note in shown:
        out = NOTES / f"{note['slug']}.html"
        out.write_text(note_page(note, css_v), encoding="utf-8")
        keep.add(out.name)
    for stale in NOTES.glob("*.html"):
        if stale.name not in keep:
            stale.unlink()
    (NOTES / "index.html").write_text(index_page(shown, css_v), encoding="utf-8")

    home = ROOT / "index.html"
    html = home.read_text(encoding="utf-8")
    nav = ('<a href="blog/index.html"><span class="en">Blog</span><span class="zh">博客</span></a>'
           if shown else "")
    home.write_text(replace_block(html, "blog-nav", nav), encoding="utf-8")
    print(f"blog: {len(shown)} built ({sum(n['draft'] for n in shown)} drafts), {len(notes)} sources")


if __name__ == "__main__":
    main()
