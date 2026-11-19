"""Getting the prices: ask GOV.UK's Content API where the latest CSV is, then download and read it.

The government republishes the weekly fuel prices CSV every Monday/Tuesday under a new file URL, so the
URL can't be hard-coded. The Content API is a public JSON API (no key needed) that describes the page,
including its current attachments, so the robot asks it for the link each time.
"""
import csv
import io
from datetime import date, datetime

import requests

CONTENT_API = "https://www.gov.uk/api/content/government/statistics/weekly-road-fuel-prices"
TIMEOUT = 30  # seconds


class SourceError(Exception):
    """The data source changed shape or couldn't be reached."""


def find_csv_url(page):
    """Pick the CSV that covers 2018 to now out of the page's attachments."""
    attachments = page.get("details", {}).get("attachments", [])
    csvs = [a for a in attachments if a.get("content_type") == "text/csv" and a.get("url")]
    for a in csvs:
        if "2018" in a.get("title", ""):
            return a["url"]
    # Fall back to any CSV that isn't the old 2003-2017 archive
    current = [a for a in csvs if "2003" not in a.get("title", "")]
    if current:
        return current[0]["url"]
    raise SourceError("Couldn't find the weekly prices CSV on the GOV.UK page")


def _find_column(header, *words):
    for i, name in enumerate(header):
        if all(w.lower() in name.lower() for w in words):
            return i
    raise SourceError(f"CSV has no column containing {words}. Header was: {header}")


def to_hundredths(text):
    """'167.07' -> 16707. Prices are kept as whole hundredths of a penny so maths on them is exact."""
    whole, _, frac = text.strip().partition(".")
    frac = (frac + "00")[:2]
    return int(whole) * 100 + int(frac)


def parse_prices(csv_text):
    """Turn the CSV into [(week, petrol, diesel), ...], prices in hundredths of a penny per litre."""
    rows = list(csv.reader(io.StringIO(csv_text.lstrip("﻿"))))
    if not rows:
        raise SourceError("CSV was empty")
    header = rows[0]
    i_date = _find_column(header, "date")
    i_petrol = _find_column(header, "ULSP", "pump price")
    i_diesel = _find_column(header, "ULSD", "pump price")

    prices = []
    for row in rows[1:]:
        if len(row) <= max(i_date, i_petrol, i_diesel) or not row[i_date].strip():
            continue  # blank or footer line
        try:
            week = datetime.strptime(row[i_date].strip(), "%d/%m/%Y").date()
            prices.append((week, to_hundredths(row[i_petrol]), to_hundredths(row[i_diesel])))
        except ValueError:
            continue  # notes or other non-data rows
    if not prices:
        raise SourceError("CSV had no rows with prices in")
    return sorted(prices)


def fetch_prices(session=None):
    """Ask the API for the CSV link, download it and return the parsed weekly prices."""
    http = session or requests.Session()
    try:
        page = http.get(CONTENT_API, timeout=TIMEOUT)
        page.raise_for_status()
        url = find_csv_url(page.json())
        data = http.get(url, timeout=TIMEOUT)
        data.raise_for_status()
    except requests.RequestException as exc:
        raise SourceError(f"Couldn't download the prices: {exc}") from exc
    return parse_prices(data.content.decode("utf-8-sig", errors="replace"))


def format_pence(hundredths):
    return f"{hundredths // 100}.{hundredths % 100:02d}p"


def week_label(week):
    if isinstance(week, str):
        week = date.fromisoformat(week)
    return week.strftime("%d %b %Y")
