# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "beautifulsoup4",
# ]
# ///

"""
Fetches and parses fundamental data from IndoPremier for any IDX stock ticker.

Usage (as a module):
    from indopremier_fundamental import fetch_fundamental

    data = fetch_fundamental("BBCA")          # annual (auto)
    data = fetch_fundamental("BBCA", quarter=1)  # Q1 / 3-month view
"""

from __future__ import annotations

import csv
import io
import json
import httpx
from bs4 import BeautifulSoup

OutputFormat = str  # Literal["dict", "json", "str", "csv"]

BASE_URL = "https://www.indopremier.com/module/saham/include/fundamental.php"

QUARTER_LABELS = {
    None: "Annual (Auto)",
    1: "3 Month (Q1)",
    2: "6 Month (H1)",
    3: "9 Month (Q1-Q3)",
    4: "12 Month (Full Year)",
    5: "Every Quarter",
}

# Section header text as it appears in the HTML
_SECTION_MAP = {
    "BALANCE SHEET": "balance_sheet",
    "INCOME STATEMENT": "income_statement",
    "RATIO": "ratio",
}


def _parse_value(raw: str) -> str:
    """Return the value stripped of extra whitespace. Keeps units (T, B, %, x) intact."""
    return raw.strip()


def _parse_table(soup: BeautifulSoup) -> tuple[list[str], dict]:
    """
    Parse the fundamental table from the BeautifulSoup object.

    Returns:
        columns  : list of period column headers, e.g. ["Anlz 2025", "[12M] 2025", ...]
        sections : nested dict of {section -> {metric -> {period -> value}}}
    """
    table = soup.find("table", class_="table-fundamental")
    if table is None:
        raise ValueError("Fundamental table not found in response.")

    # --- Column headers ---
    header_row = table.find("thead").find("tr")
    # Skip the first two <th> (dropdown + GO button), rest are period labels
    header_cells = header_row.find_all("th")[2:]
    columns = [th.get_text(strip=True) for th in header_cells]

    # --- Body rows ---
    sections: dict[str, dict[str, dict[str, str]]] = {
        "overview": {},
        "balance_sheet": {},
        "income_statement": {},
        "ratio": {},
    }
    current_section = "overview"

    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")

        # Section header row: single cell spanning all columns with <strong> text
        if len(cells) == 1 or (len(cells) >= 1 and cells[0].get("colspan")):
            text = cells[0].get_text(strip=True)
            if text in _SECTION_MAP:
                current_section = _SECTION_MAP[text]
                continue

        # Skip rows that don't have enough cells to match columns
        # Layout: [label (colspan=2)] + one td per column
        value_cells = [c for c in cells if not c.get("colspan")]
        label_cells = [c for c in cells if c.get("colspan") == "2"]

        if not label_cells or not value_cells:
            continue

        metric = label_cells[0].get_text(strip=True)
        if not metric:
            continue

        values = {
            col: _parse_value(value_cells[i].get_text())
            for i, col in enumerate(columns)
            if i < len(value_cells)
        }

        sections[current_section][metric] = values

    return columns, sections


def _to_csv(data: dict) -> str:
    """Flatten sections into a CSV: section, metric, then one column per period."""
    buf = io.StringIO()
    columns = data["columns"]
    writer = csv.writer(buf)
    writer.writerow(["section", "metric"] + columns)
    for section, metrics in data["sections"].items():
        for metric, values in metrics.items():
            row = [section, metric] + [values.get(col, "") for col in columns]
            writer.writerow(row)
    return buf.getvalue()


def _to_str(data: dict) -> str:
    """Human-readable plain-text representation."""
    lines = [
        f"Stock: {data['stock']}",
        f"Period: {data['quarter_label']}",
        f"Columns: {', '.join(data['columns'])}",
        "",
    ]
    for section, metrics in data["sections"].items():
        if not metrics:
            continue
        lines.append(f"[{section.upper().replace('_', ' ')}]")
        for metric, values in metrics.items():
            vals = "  |  ".join(
                f"{col}: {values.get(col, '-')}" for col in data["columns"]
            )
            lines.append(f"  {metric:<20} {vals}")
        lines.append("")
    return "\n".join(lines)


def fetch_fundamental(
    code: str,
    quarter: int | None = None,
    output: OutputFormat = "dict",
) -> dict | str:
    """
    Fetch and parse fundamental data for an IDX stock from IndoPremier.

    Args:
        code    : IDX stock ticker, e.g. "BBCA", "TLKM", "GOTO"
        quarter : Reporting period slice:
                    None → Annual / Auto (default)
                    1    → 3-month  (Q1 YTD)
                    2    → 6-month  (H1 YTD)
                    3    → 9-month  (Q1-Q3 YTD)
                    4    → 12-month (full year, same as None)
                    5    → Every quarter side-by-side
        output  : Return format — "dict" | "json" | "str" | "csv"
                    "dict" → Python dict (default)
                    "json" → JSON-formatted string
                    "str"  → Plain-text human-readable summary
                    "csv"  → CSV table (section, metric, period columns...)

    Returns:
        dict if output="dict", otherwise a str.
    """
    if quarter is not None and quarter not in (1, 2, 3, 4, 5):
        raise ValueError(f"quarter must be 1–5 or None, got {quarter!r}")
    if output not in ("dict", "json", "str", "csv"):
        raise ValueError(
            f"output must be 'dict', 'json', 'str', or 'csv', got {output!r}"
        )

    params: dict = {"code": code.upper()}
    if quarter is not None:
        params["quarter"] = quarter

    response = httpx.get(BASE_URL, params=params, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    columns, sections = _parse_table(soup)

    data = {
        "stock": code.upper(),
        "quarter": quarter,
        "quarter_label": QUARTER_LABELS.get(quarter, str(quarter)),
        "columns": columns,
        "sections": sections,
    }

    if output == "dict":
        return data
    if output == "json":
        return json.dumps(data)
    if output == "csv":
        return _to_csv(data)
    # output == "str"
    return _to_str(data)


if __name__ == "__main__":
    import sys

    fmt = sys.argv[1] if len(sys.argv) > 1 else "str"
    result = fetch_fundamental("BBCA", quarter=1, output=fmt)
    if isinstance(result, dict):

        print(json.dumps(result, indent=2))
    else:
        print(result)
