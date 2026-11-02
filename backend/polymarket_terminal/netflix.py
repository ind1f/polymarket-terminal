import html
import re
import time

import httpx

BASE_URL = "https://www.netflix.com/tudum/top10"
PATHS = {
    ("global", "tv"): "/tv",
    ("global", "films"): "",
    ("us", "tv"): "/united-states/tv",
    ("us", "films"): "/united-states",
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
}
PERIOD = re.compile(r"\d{2}/\d{2}/\d{2} - \d{2}/\d{2}/\d{2}")
ROW = re.compile(r'<span class="rank">(\d+)</span>.*?<button>(.*?)</button>(.*?)</tr>', re.S)
CELL = re.compile(r"<td[^>]*>([^<]*)</td>")


def parse_page(page: str, region: str, kind: str) -> dict:
    start = page.index("<table")
    end = page.index("</table>", start)
    periods = PERIOD.findall(page[:start])
    rows = []
    for rank, title, rest in ROW.findall(page[start:end]):
        cells = [html.unescape(cell).strip() for cell in CELL.findall(rest)]
        weeks = _number(cells[0]) if cells else None
        values = [weeks, _number(cells[1]) if len(cells) > 1 else None] if region == "global" else [weeks]
        rows.append({"rank": int(rank), "name": html.unescape(title).strip(), "values": values})
    if not rows:
        raise ValueError("Netflix Top 10 table has no rows")
    columns = [{"label": "Weeks", "kind": "count"}]
    if region == "global":
        columns.append({"label": "Views", "kind": "count"})
    place = "Global (English)" if region == "global" else "US"
    return {
        "title": f"Netflix Top 10 {'Shows' if kind == 'tv' else 'Movies'} · {place}",
        "period": f"Latest published week {periods[-1]}" if periods else None,
        "rank_label": "Last wk",
        "columns": columns,
        "rows": rows,
    }


def _number(text: str) -> int | None:
    digits = text.replace(",", "")
    return int(digits) if digits.isdigit() else None


async def fetch_chart(client: httpx.AsyncClient, region: str, kind: str) -> dict:
    response = await client.get(
        BASE_URL + PATHS[(region, kind)], headers=HEADERS, follow_redirects=True
    )
    response.raise_for_status()
    return parse_page(response.text, region, kind) | {"fetched_ms": int(time.time() * 1000)}
