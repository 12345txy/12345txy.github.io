"""Render papers into the homepage so static readers and search engines see the same data."""

from datetime import date
import hashlib
import re
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "dist" if (ROOT / "dist/index.html").is_file() else ROOT

TOPICS = [
    ("agents", "Agents & LLM systems", "智能体与 LLM 系统"),
    ("multimodal", "Multimodal evaluation", "多模态评测"),
    ("compression", "Model compression", "模型压缩"),
]
LINK_LABELS = {"Code": "Code", "Model": "Model", "Project page": "Project"}
LINK_ICONS = {"Code": "code", "Model": "cube", "Project page": "link"}


def bilingual(english, chinese):
    return f'<span class="en">{escape(english)}</span><span class="zh">{escape(chinese)}</span>'


def tagged_author(name):
    clean = escape(name.rstrip("*"))
    if clean == "Xinyu Tan":
        clean = f'<b class="me">{clean}</b>'
    return clean + ("<sup>*</sup>" if name.endswith("*") else "")


def is_cofirst(paper):
    return any(name.rstrip("*") == "Xinyu Tan" and name.endswith("*") for name in paper["authors"])


def paper_html(paper):
    url = escape(paper["paperUrl"], quote=True)
    title = escape(paper["title"])
    slug = escape(paper["id"], quote=True)
    tags = [paper["topic"]] + (["cofirst"] if is_cofirst(paper) else [])
    authors = ", ".join(tagged_author(name) for name in paper["authors"])

    venue = f'<span class="venue">{escape(paper["venueLabel"])}</span>'
    if paper.get("venueNote"):
        venue += f'<span class="venue-note">{bilingual(paper["venueNote"]["en"], paper["venueNote"]["zh"])}</span>'

    links = [f'<a class="pl" href="{url}"><svg aria-hidden="true"><use href="#paper"/></svg>arXiv</a>']
    for link in paper["links"]:
        label = link["label"]
        if label not in LINK_LABELS:
            continue
        icon = LINK_ICONS[label]
        links.append(
            f'<a class="pl" href="{escape(link["url"], quote=True)}"><svg aria-hidden="true"><use href="#{icon}"/></svg>{LINK_LABELS[label]}</a>'
        )
    stat = paper["citations"]
    count = stat["count"]
    if count > 0:
        links.append(
            f'<a class="cites" href="{escape(stat["url"], quote=True)}" title="OpenAlex · {escape(stat["checkedAt"])}">'
            + bilingual(f"{count} citations", f"被引 {count}") + "</a>"
        )
    role = ""
    if paper.get("role"):
        role = f'<span class="role">{bilingual(paper["role"]["en"], paper["role"]["zh"])}</span>'

    featured = " featured" if paper.get("featured") else ""
    summary = paper.get("summary", {})
    return f'''<article class="paper{featured}" data-tags="{' '.join(tags)}">
  <a class="thumb" href="{url}" aria-label="{title}"><img src="assets/{slug}.webp" loading="lazy" alt=""></a>
  <div class="paper-body">
    <h3><a href="{url}">{title}</a></h3>
    <p class="authors">{authors}</p>
    <p class="summary">{bilingual(summary.get("en", ""), summary.get("zh", ""))}</p>
    <p class="paper-foot">{venue}{''.join(links)}{role}</p>
  </div>
</article>'''


def filters_html(papers):
    counts = {key: sum(p["topic"] == key for p in papers) for key, _, _ in TOPICS}
    buttons = [("all", "All", "全部", len(papers)), ("cofirst", "Co-first author", "共同一作", sum(map(is_cofirst, papers)))]
    buttons += [(key, en, zh, counts[key]) for key, en, zh in TOPICS if counts[key]]
    return "\n".join(
        f'<button type="button" data-filter="{key}" aria-pressed="{str(key == "all").lower()}">'
        f'{bilingual(en, zh)}<span class="count">{n}</span></button>'
        for key, en, zh, n in buttons
    )


def replace_block(html, key, content):
    start, end = f"<!-- {key}:start -->", f"<!-- {key}:end -->"
    before, found, tail = html.partition(start)
    _, closing, after = tail.partition(end)
    if not found or not closing:
        raise ValueError(f"Missing HTML markers for {key}")
    return f"{before}{start}\n{content}\n{end}{after}"


def bust_cache(html):
    """Version CSS/JS links by content hash so browsers never pair new HTML with stale assets."""
    for name in ("style.css", "site.js"):
        digest = hashlib.sha1((PUBLIC / "assets" / name).read_bytes()).hexdigest()[:10]
        html, n = re.subn(rf'assets/{re.escape(name)}(\?v=[0-9a-f]+)?"', f'assets/{name}?v={digest}"', html)
        if n != 1:
            raise ValueError(f"Expected one link to assets/{name}, found {n}")
    return html


def main():
    papers = json.loads((PUBLIC / "data/publications.json").read_text())["papers"]
    dates = sorted({date.fromisoformat(p["citations"]["checkedAt"]).isoformat() for p in papers})
    checked = dates[-1]
    count = sum(p["citations"]["count"] for p in papers)
    summary = (
        '<p class="source-note">' + bilingual(f"{len(papers)} papers", f"{len(papers)} 篇论文")
        + " · " + bilingual(f"{count} citations", f"总被引 {count} 次")
        + f' · <a href="https://openalex.org/">OpenAlex</a> {checked}'
        + " · " + bilingual("* equal contribution", "* 共同一作") + "</p>"
    )
    stat = f'<b>{count}</b>{bilingual("citations", "总被引")}'
    path = PUBLIC / "index.html"
    html = path.read_text()
    html = replace_block(html, "citation-summary", summary)
    html = replace_block(html, "citation-stat", stat)
    html = replace_block(html, "updated", checked)
    html = replace_block(html, "filters", filters_html(papers))
    html = bust_cache(html)
    path.write_text(replace_block(html, "publications", "\n".join(map(paper_html, papers))))


if __name__ == "__main__":
    main()
