"""The robot's daily job. GitHub Actions runs this every morning:

    python -m robot.run --alert-file alert.md

1. fetch the latest weekly prices from GOV.UK
2. save any new (or revised) weeks to data/prices.db
3. redraw charts/prices.png if anything changed
4. if a new week came in and petrol or diesel moved more than 5%, write alert.md
   (the workflow turns that file into a GitHub issue, which emails me)
"""
import argparse
import os
import sys
from pathlib import Path

from robot import alert, chart, source, store


def run(conn, fetch=source.fetch_prices, alert_file=None, owner=None, test_alert=False, chart_path=None):
    try:
        prices = fetch()
    except source.SourceError as exc:
        store.log_run(conn, "failed", message=str(exc))
        print(f"FAILED: {exc}")
        return 1

    new_weeks, changed = store.save_prices(conn, prices)
    recent = store.latest_weeks(conn, 2)
    latest = recent[0]
    summary = (f"{new_weeks} new week(s), {changed} revised. Latest: {source.week_label(latest['week'])} "
               f"petrol {source.format_pence(latest['petrol'])}, diesel {source.format_pence(latest['diesel'])}")
    store.log_run(conn, "ok", new_weeks, changed, summary)
    print(summary)
    if chart_path and (new_weeks or changed or not Path(chart_path).exists()):
        chart.draw(conn, chart_path)
    if len(recent) < 2:
        return 0  # need two weeks to compare
    previous = recent[1]

    # Only alert when a new week arrives, otherwise the same jump would be reported every day until next week
    jumps = alert.check_for_jumps(latest, previous) if new_weeks else []
    if (jumps or test_alert) and alert_file:
        Path(alert_file).write_text(alert.alert_text(latest, previous, jumps, owner, test=not jumps), encoding="utf-8")
        print(f"Alert written to {alert_file}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect the latest UK fuel prices")
    parser.add_argument("--db", default=store.DEFAULT_DB)
    parser.add_argument("--alert-file", help="where to write the alert, if there is one")
    parser.add_argument("--chart", default=chart.DEFAULT_CHART, help="where to save the chart")
    parser.add_argument("--test-alert", action="store_true", help="write an alert even if prices didn't jump")
    args = parser.parse_args(argv)
    conn = store.connect(args.db)
    return run(conn, alert_file=args.alert_file, owner=os.environ.get("ALERT_MENTION"), test_alert=args.test_alert,
               chart_path=args.chart)


if __name__ == "__main__":
    sys.exit(main())
