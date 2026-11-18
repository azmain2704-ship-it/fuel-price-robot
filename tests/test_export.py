import csv
from datetime import date

from robot import run, source, store
from tests.test_robot import CSV_TEXT


def test_export_writes_plain_pence(tmp_path):
    conn = store.connect(tmp_path / "prices.db")
    store.save_prices(conn, [(date(2026, 11, 9), 17071, 19819), (date(2026, 11, 16), 16707, 19677)])
    out = store.export_csv(conn, tmp_path / "prices.csv")
    with open(out, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows == [["week", "petrol_pence", "diesel_pence"],
                    ["2026-11-09", "170.71", "198.19"],
                    ["2026-11-16", "167.07", "196.77"]]


def test_pence_keep_their_zeros():
    assert store.pence_text(15005) == "150.05"
    assert store.pence_text(15000) == "150.00"


def test_csv_is_only_rewritten_when_prices_change(tmp_path):
    conn = store.connect(tmp_path / "prices.db")
    out = tmp_path / "prices.csv"
    run.run(conn, fetch=lambda: source.parse_prices(CSV_TEXT), csv_path=out)
    assert out.exists()
    before = out.stat().st_mtime_ns
    run.run(conn, fetch=lambda: source.parse_prices(CSV_TEXT), csv_path=out)  # nothing new
    assert out.stat().st_mtime_ns == before
