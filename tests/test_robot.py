import json
from datetime import date
from pathlib import Path

import pytest
import requests

from robot import alert, chart, run, source, store

FIXTURES = Path(__file__).parent / "fixtures"
CSV_TEXT = (FIXTURES / "weekly_prices.csv").read_text(encoding="utf-8")
PAGE = json.loads((FIXTURES / "content_api_page.json").read_text())


@pytest.fixture
def conn(tmp_path):
    return store.connect(tmp_path / "test.db")


def week(d, petrol, diesel):
    return (date.fromisoformat(d), petrol, diesel)


# --- reading the source -------------------------------------------------------------------

def test_finds_the_2018_onwards_csv_not_the_old_archive():
    assert source.find_csv_url(PAGE).endswith("CSV__2018_-__.csv")


def test_missing_csv_is_a_clear_error():
    with pytest.raises(source.SourceError):
        source.find_csv_url({"details": {"attachments": []}})


def test_parses_real_csv_format():
    prices = source.parse_prices(CSV_TEXT)
    assert len(prices) == 6
    assert prices[-1] == (date(2026, 11, 16), 16707, 19677)


def test_handles_byte_order_mark_and_blank_lines():
    prices = source.parse_prices("﻿" + CSV_TEXT + "\n\n,,,\n")
    assert len(prices) == 6


def test_price_conversion_is_exact():
    assert source.to_hundredths("167.07") == 16707
    assert source.to_hundredths("167.1") == 16710
    assert source.to_hundredths("167") == 16700
    assert source.format_pence(16707) == "167.07p"


def test_changed_column_names_fail_loudly():
    with pytest.raises(source.SourceError):
        source.parse_prices("Date,Something else\n16/11/2026,1\n")


class FakeResponse:
    def __init__(self, json_data=None, content=b"", status=200):
        self._json, self.content, self.status_code = json_data, content, status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    def __init__(self, csv_status=200):
        self.csv_status = csv_status
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        if url == source.CONTENT_API:
            return FakeResponse(json_data=PAGE)
        return FakeResponse(content=CSV_TEXT.encode(), status=self.csv_status)


def test_fetch_asks_the_api_then_downloads_the_csv():
    session = FakeSession()
    prices = source.fetch_prices(session)
    assert session.urls[0] == source.CONTENT_API
    assert session.urls[1].endswith(".csv")
    assert len(prices) == 6


def test_download_failure_becomes_source_error():
    with pytest.raises(source.SourceError):
        source.fetch_prices(FakeSession(csv_status=503))


# --- saving -------------------------------------------------------------------------------

def test_saving_twice_doesnt_duplicate(conn):
    prices = source.parse_prices(CSV_TEXT)
    assert store.save_prices(conn, prices) == (6, 0)
    assert store.save_prices(conn, prices) == (0, 0)
    assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 6


def test_revised_numbers_are_updated(conn):
    store.save_prices(conn, [week("2026-11-16", 16707, 19677)])
    assert store.save_prices(conn, [week("2026-11-16", 16710, 19677)]) == (0, 1)
    assert store.latest_weeks(conn, 1)[0]["petrol"] == 16710


# --- the alert ----------------------------------------------------------------------------

def test_small_moves_dont_alert():
    prev, latest = {"petrol": 17071, "diesel": 19819}, {"petrol": 16707, "diesel": 19677}  # about -2%
    assert alert.check_for_jumps(latest, prev) == []


def test_big_jump_alerts():
    prev, latest = {"petrol": 15000, "diesel": 16000}, {"petrol": 15900, "diesel": 16100}  # +6% and +0.6%
    jumps = alert.check_for_jumps(latest, prev)
    assert [j[0] for j in jumps] == ["petrol"]
    assert jumps[0][3] == pytest.approx(6.0)


def test_exactly_five_percent_is_not_more_than_five():
    assert alert.check_for_jumps({"petrol": 10500, "diesel": 10000}, {"petrol": 10000, "diesel": 10000}) == []


# --- a whole run --------------------------------------------------------------------------

def test_first_run_saves_history_and_logs_it(conn, tmp_path):
    code = run.run(conn, fetch=lambda: source.parse_prices(CSV_TEXT), alert_file=tmp_path / "alert.md")
    assert code == 0
    assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 6
    last = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchone()
    assert last["status"] == "ok" and last["new_weeks"] == 6
    assert not (tmp_path / "alert.md").exists()  # nothing jumped 5%


def test_new_week_with_big_jump_writes_alert(conn, tmp_path):
    store.save_prices(conn, [week("2026-11-09", 15000, 16000)])
    alert_file = tmp_path / "alert.md"
    run.run(conn, fetch=lambda: [week("2026-11-09", 15000, 16000), week("2026-11-16", 16000, 16100)],
            alert_file=alert_file, owner="someone")
    text = alert_file.read_text()
    assert text.startswith("Fuel price alert: petrol up 6.7%")
    assert "| Petrol | 150.00p | 160.00p | +6.7% |" in text
    assert "@someone" in text


def test_same_jump_isnt_reported_again_the_next_day(conn, tmp_path):
    data = [week("2026-11-09", 15000, 16000), week("2026-11-16", 16000, 16100)]
    run.run(conn, fetch=lambda: data)                     # day 1: new week saved
    alert_file = tmp_path / "alert.md"
    run.run(conn, fetch=lambda: data, alert_file=alert_file)  # day 2: nothing new
    assert not alert_file.exists()


def test_test_alert_can_be_forced(conn, tmp_path):
    alert_file = tmp_path / "alert.md"
    run.run(conn, fetch=lambda: source.parse_prices(CSV_TEXT), alert_file=alert_file, test_alert=True)
    assert alert_file.read_text().startswith("Test alert")


def test_failed_fetch_is_logged_and_returns_error(conn):
    def broken():
        raise source.SourceError("GOV.UK was down")

    assert run.run(conn, fetch=broken) == 1
    last = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchone()
    assert last["status"] == "failed" and "GOV.UK was down" in last["message"]


def test_chart_is_drawn_when_prices_change(conn, tmp_path):
    png = tmp_path / "prices.png"
    run.run(conn, fetch=lambda: source.parse_prices(CSV_TEXT), chart_path=png)
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    before = png.stat().st_mtime_ns
    run.run(conn, fetch=lambda: source.parse_prices(CSV_TEXT), chart_path=png)  # nothing new
    assert png.stat().st_mtime_ns == before


def test_chart_needs_two_weeks(conn, tmp_path):
    store.save_prices(conn, [week("2026-11-16", 16707, 19677)])
    assert chart.draw(conn, tmp_path / "c.png") is None
