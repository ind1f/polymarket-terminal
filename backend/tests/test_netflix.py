import pytest

from polymarket_terminal.netflix import parse_page


def page(rows: str, global_columns: bool = True) -> str:
    extra = "<td>6,200,000</td><td>4:45</td><td>29,400,000</td>" if global_columns else ""
    body = "".join(
        f'<tr><td class="title"><span class="rank">{rank:02d}</span><img/>'
        f"<button>{title}</button></td><td>{weeks}</td>{extra}</tr>"
        for rank, title, weeks in rows
    )
    return (
        "<div>Global</div><div>10/12/26 - 10/18/26</div><div>10/19/26 - 10/25/26</div>"
        f"<table><tbody>{body}</tbody></table>"
        '<table><tr><td class="title"><span class="rank">01</span><button>Other table</button></td></tr></table>'
    )


def test_global_page_has_weeks_views_and_latest_period():
    chart = parse_page(page([(1, "Below: Limited Series", 3), (2, "Theo Von: I&#x27;m Doing Fine", 1)]), "global", "tv")
    assert chart["title"] == "Netflix Top 10 Shows · Global (English)"
    assert chart["period"] == "Latest published week 10/19/26 - 10/25/26"
    assert chart["rows"] == [
        {"rank": 1, "name": "Below: Limited Series", "values": [3, 6200000]},
        {"rank": 2, "name": "Theo Von: I'm Doing Fine", "values": [1, 6200000]},
    ]


def test_us_page_has_weeks_only():
    chart = parse_page(page([(1, "Animals", 3)], global_columns=False), "us", "films")
    assert chart["title"] == "Netflix Top 10 Movies · US"
    assert [column["label"] for column in chart["columns"]] == ["Weeks"]
    assert chart["rows"] == [{"rank": 1, "name": "Animals", "values": [3]}]


def test_empty_table_is_an_error():
    with pytest.raises(ValueError):
        parse_page(page([]), "us", "tv")


def test_missing_table_is_an_error():
    with pytest.raises(ValueError):
        parse_page("<html>redesigned</html>", "us", "tv")
