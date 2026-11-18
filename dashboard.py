"""The dashboard:  streamlit run dashboard.py

Reads data/prices.db (kept up to date by the daily GitHub Action) and shows prices over time.
"""
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from robot import forecast

DB = Path(__file__).parent / "data" / "prices.db"
PETROL, DIESEL = "#2a78d6", "#eb6834"   # same colours as my fuel prices notebook
MUTED, GRID = "#52514e", "#e4e3df"

st.set_page_config(page_title="UK fuel price robot", page_icon="⛽", layout="wide")


@st.cache_data(ttl=600)
def load():
    with sqlite3.connect(DB) as conn:
        prices = pd.read_sql("SELECT week, petrol, diesel FROM prices ORDER BY week", conn, parse_dates=["week"])
        runs = pd.read_sql("SELECT ran_at, status, new_weeks, message FROM runs ORDER BY id DESC LIMIT 14", conn)
    prices[["petrol", "diesel"]] = prices[["petrol", "diesel"]] / 100   # hundredths of a penny -> pence
    return prices, runs


st.title("UK fuel price robot")
st.caption("A GitHub Action collects the official weekly UK pump prices every morning. This page shows what it's found.")

if not DB.exists():
    st.warning("No data yet. Run `python -m robot.run` once to collect the prices.")
    st.stop()

prices, runs = load()
latest, previous = prices.iloc[-1], prices.iloc[-2]

# --- headline numbers ---
c1, c2, c3 = st.columns(3)
c1.metric("Petrol (unleaded)", f"{latest.petrol:.2f}p", f"{latest.petrol - previous.petrol:+.2f}p on last week",
          delta_color="inverse")
c2.metric("Diesel", f"{latest.diesel:.2f}p", f"{latest.diesel - previous.diesel:+.2f}p on last week",
          delta_color="inverse")
c3.metric("Latest figures", latest.week.strftime("%d %b %Y"))
if len(runs):
    c3.caption(f"Robot last ran {runs.iloc[0].ran_at[:16]} UTC ({runs.iloc[0].status})")

# --- chart ---
ranges = {"6 months": 26, "1 year": 52, "2 years": 104, "All (since 2018)": None}
choice = st.radio("Show", list(ranges), index=1, horizontal=True, label_visibility="collapsed")
weeks = ranges[choice]
shown = prices.tail(weeks) if weeks else prices

long = shown.melt("week", var_name="fuel", value_name="pence")
long["fuel"] = long["fuel"].map({"petrol": "Petrol", "diesel": "Diesel"})
colour = alt.Scale(domain=["Petrol", "Diesel"], range=[PETROL, DIESEL])

hover = alt.selection_point(fields=["week"], nearest=True, on="pointerover", empty=False)
base = alt.Chart(long).encode(
    x=alt.X("week:T", title=None, axis=alt.Axis(grid=False, labelColor=MUTED, tickColor=GRID, domainColor=GRID)),
    y=alt.Y("pence:Q", title="Pence per litre", scale=alt.Scale(zero=False),
            axis=alt.Axis(gridColor=GRID, labelColor=MUTED, titleColor=MUTED, domain=False, ticks=False)),
    color=alt.Color("fuel:N", scale=colour, legend=alt.Legend(title=None, orient="top-left")),
)
lines = base.mark_line(strokeWidth=2)
points = base.mark_point(size=60, filled=True, stroke="white", strokeWidth=2).encode(
    opacity=alt.condition(hover, alt.value(1), alt.value(0)))
rule = alt.Chart(shown).mark_rule(color=MUTED, strokeWidth=1).encode(
    x="week:T",
    opacity=alt.condition(hover, alt.value(0.5), alt.value(0)),
    tooltip=[alt.Tooltip("week:T", title="Week of", format="%d %b %Y"),
             alt.Tooltip("petrol:Q", title="Petrol (p)", format=".2f"),
             alt.Tooltip("diesel:Q", title="Diesel (p)", format=".2f")],
).add_params(hover)
ends = base.transform_filter(alt.datum.week == alt.expr.toDate(latest.week.isoformat())).mark_text(
    align="left", dx=8, fontSize=12).encode(text=alt.Text("pence:Q", format=".1f"), color=alt.value(MUTED))

chart = (lines + points + rule + ends).properties(height=380, padding={"left": 5, "top": 5, "bottom": 5, "right": 50})
st.altair_chart(chart, width="stretch")

with st.expander("See the numbers as a table"):
    table = shown.sort_values("week", ascending=False).rename(
        columns={"week": "Week", "petrol": "Petrol (p)", "diesel": "Diesel (p)"})
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"Week": st.column_config.DateColumn(format="DD MMM YYYY")})

# --- forecast ---
st.subheader("Next 4 weeks: a forecast, and how much to trust it")


@st.cache_data(ttl=600)
def run_forecast(fuel):
    with sqlite3.connect(DB) as conn:
        series = forecast.load_series(conn, fuel)
    return series, forecast.forecast(series), forecast.backtest(series), forecast.carry_over(series)


fuel = st.radio("Fuel", ["Petrol", "Diesel"], horizontal=True, key="forecast_fuel")
series, ahead, scores, carry = run_forecast(fuel.lower())
colour = PETROL if fuel == "Petrol" else DIESEL

for col, (week, pence) in zip(st.columns(len(ahead)), ahead):
    col.metric(f"w/c {week:%d %b}", f"{pence:.1f}p")

past = pd.DataFrame({"week": [w for w, _ in series[-26:]], "pence": [p for _, p in series[-26:]], "kind": "Actual"})
future = pd.DataFrame({"week": [series[-1][0]] + [w for w, _ in ahead],
                       "pence": [series[-1][1]] + [p for _, p in ahead], "kind": "Forecast"})
both = pd.concat([past, future])
both["week"] = pd.to_datetime(both["week"])
fc_chart = alt.Chart(both).mark_line(strokeWidth=2).encode(
    x=alt.X("week:T", title=None, axis=alt.Axis(grid=False, labelColor=MUTED, tickColor=GRID, domainColor=GRID)),
    y=alt.Y("pence:Q", title="Pence per litre", scale=alt.Scale(zero=False),
            axis=alt.Axis(gridColor=GRID, labelColor=MUTED, titleColor=MUTED, domain=False, ticks=False)),
    color=alt.Color("kind:N", scale=alt.Scale(domain=["Actual", "Forecast"], range=[MUTED, colour]),
                    legend=alt.Legend(title=None, orient="top-left")),
    strokeDash=alt.StrokeDash("kind:N", scale=alt.Scale(domain=["Actual", "Forecast"], range=[[1, 0], [6, 4]]),
                              legend=None),
    tooltip=[alt.Tooltip("week:T", title="Week", format="%d %b %Y"), alt.Tooltip("kind:N", title=""),
             alt.Tooltip("pence:Q", title="Pence", format=".1f")],
).properties(height=300)
st.altair_chart(fc_chart, width="stretch")

st.markdown(
    f"**How good is it?** I replayed the last {scores['weeks_tested']} weeks, predicting each one using only the "
    f"weeks before it. Average miss for next week's {fuel.lower()} price:")
st.dataframe(pd.DataFrame({
    "Method": ["Momentum (this forecast)", "Repeat last week's change", "Same as last week", "Straight line (4 weeks)"],
    "Average miss (p)": [scores["momentum"], scores["repeat"], scores["naive"], scores["line"]],
}), hide_index=True)
st.caption(f"Price changes tend to carry on: about {carry:.0%} of one week's {fuel.lower()} change carries into the "
           "next, and the forecast uses that. It can't see shocks coming, and it gets less reliable the further "
           "ahead it looks, so treat it as a guide.")

# --- robot log ---
st.subheader("What the robot's been doing")
st.caption("One row per run. New figures come out once a week, so most days it finds nothing new, which is fine.")
st.dataframe(runs.rename(columns={"ran_at": "Ran at (UTC)", "status": "Status", "new_weeks": "New weeks",
                                  "message": "Details"}), hide_index=True, width="stretch")

st.caption("Data: Department for Energy Security and Net Zero, weekly road fuel prices "
           "(Open Government Licence v3.0), fetched through the GOV.UK Content API.")
