"""Refresh OpenAlex cited-by counts for the arXiv papers listed on the site."""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "dist" if (ROOT / "dist/index.html").is_file() else ROOT
DATA = PUBLIC / "data" / "publications.json"


def get_citation(paper):
    match = re.fullmatch(r"https://arxiv\.org/abs/(\d{4}\.\d{4,5})(?:v\d+)?", paper["paperUrl"])
    if not match:
        raise ValueError(f"Unrecognized arXiv URL {paper['paperUrl']}")
    doi = "https://doi.org/10.48550/arxiv." + match[1]
    params = {"select": "id,doi,cited_by_count"}
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    request = Request(
        "https://api.openalex.org/works/" + doi + "?" + urlencode(params),
        headers={"Accept": "application/json", "User-Agent": "XinyuTanHomepage/1.0"},
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                work = json.load(response)
            break
        except HTTPError as err:
            if attempt == 2 or (err.code != 429 and err.code < 500):
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** (attempt + 1))

    count = work.get("cited_by_count")
    if (work.get("doi") or "").lower() != doi or type(count) is not int or count < 0:
        raise ValueError("OpenAlex did not return the requested DOI and a valid count")
    if not re.fullmatch(r"https://openalex\.org/W\d+", work.get("id") or ""):
        raise ValueError("OpenAlex returned an invalid work link")
    return {
        "count": count,
        "source": "OpenAlex",
        "url": work["id"],
        "checkedAt": datetime.now(timezone.utc).date().isoformat(),
    }


def main():
    publications = json.loads(DATA.read_text(encoding="utf-8"))
    refreshed = 0
    for paper in publications["papers"]:
        try:
            citation = get_citation(paper)
        except (HTTPError, URLError, TimeoutError, ValueError) as err:
            print(f"{paper['id']}: retaining the previous citation snapshot ({err})", file=sys.stderr)
            continue
        paper["citations"] = citation
        refreshed += 1
        print(f"{paper['id']}: {citation['count']} citations on {citation['checkedAt']}")
    if not refreshed:
        return 1

    # Publish a consistent snapshot even when one work was temporarily unavailable.
    with NamedTemporaryFile(mode="w", dir=DATA.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(publications, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
    path = Path(tmp.name)
    path.chmod(DATA.stat().st_mode & 0o777)
    path.replace(DATA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
