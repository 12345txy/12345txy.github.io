"""Render papers into the homepage so static readers and search engines see the same data."""

from datetime import date
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "dist" if (ROOT / "dist/index.html").is_file() else ROOT


def bilingual(english, chinese):
    return f'<span class="en">{escape(english)}</span><span class="zh">{escape(chinese)}</span>'


def tagged_author(name):
    clean = escape(name.rstrip("*"))
    if clean == "Xinyu Tan":
        clean = f"<strong>{clean}</strong>"
    return clean + ("<sup>*</sup>" if name.endswith("*") else "")


def paper_html(paper):
    preprint = paper["venue"] == "arXiv preprint"
    kind = "preprint" if preprint else "conference"
    badge = bilingual("Preprint", "预印本") if preprint else "ICML"
    meta = str(paper["year"]) if preprint else bilingual(f'{paper["year"]} · Poster', f'{paper["year"]} · 海报')
    authors = ", ".join(tagged_author(name) for name in paper["authors"])
    if any(name.endswith("*") for name in paper["authors"]):
        authors += "<small>" + bilingual("* Equal contribution", "* 共同一作") + "</small>"
    url = escape(paper["paperUrl"], quote=True)
    title = escape(paper["title"])
    slug = escape(paper["id"], quote=True)
    labels = {"Code": "代码", "Model": "模型", "Project page": "项目主页"}
    links = [f'<a href="{url}"><svg aria-hidden="true"><use href="#paper"/></svg>arXiv</a>']
    for link in paper["links"]:
        label = link["label"]
        if label == "Google Scholar":
            continue
        text = bilingual(label, labels.get(label, label))
        links.append(f'<a href="{escape(link["url"], quote=True)}">{text}</a>')
    stat = paper["citations"]
    count = stat["count"]
    checked = escape(stat["checkedAt"])
    links.append(
        f'<a class="cited" href="{escape(stat["url"], quote=True)}" title="OpenAlex · {checked}">'
        + bilingual(f"{count} citations", f"{count} 次引用") + "</a>"
    )
    return f'''<article class="paper {kind}" data-type="{kind}">
  <a class="fig" href="{url}" aria-label="{title}"><img src="assets/{slug}.webp" loading="lazy" alt=""></a>
  <div><p class="meta"><span class="venue">{badge}</span><span>{meta}</span></p>
    <h3 lang="en"><a href="{url}">{title}</a></h3>
    <p class="authors">{authors}</p>
    <p class="paper-links">{' '.join(links)}</p>
  </div>
</article>'''


def replace_block(html, key, content):
    start, end = f"<!-- {key}:start -->", f"<!-- {key}:end -->"
    before, found, tail = html.partition(start)
    _, closing, after = tail.partition(end)
    if not found or not closing:
        raise ValueError(f"Missing HTML markers for {key}")
    return f"{before}{start}\n{content}\n{end}{after}"


def main():
    papers = json.loads((PUBLIC / "data/publications.json").read_text())["papers"]
    dates = sorted({date.fromisoformat(p["citations"]["checkedAt"]).isoformat() for p in papers})
    checked = dates[0] if len(dates) == 1 else f"{dates[0]} – {dates[-1]}"
    count = sum(p["citations"]["count"] for p in papers)
    summary = (
        '<p class="source-note">' + bilingual(f"{len(papers)} papers", f"{len(papers)} 篇论文")
        + '<span class="sep" aria-hidden="true">/</span><strong>'
        + bilingual(f"{count} citations", f"{count} 次引用") + "</strong><span>· OpenAlex</span>"
        + f'<span class="sep" aria-hidden="true">/</span><span>{checked}</span></p>'
    )
    path = PUBLIC / "index.html"
    html = replace_block(path.read_text(), "citation-summary", summary)
    path.write_text(replace_block(html, "publications", "\n".join(map(paper_html, papers))))


if __name__ == "__main__":
    main()
