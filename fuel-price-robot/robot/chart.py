"""Draws charts/prices.png from the database. The robot redraws it whenever a new week comes in,
so the chart at the top of the README is always up to date without me touching it."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no screen on GitHub's servers
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from datetime import date  # noqa: E402

DEFAULT_CHART = Path(__file__).resolve().parent.parent / "charts" / "prices.png"
PETROL, DIESEL = "#2a78d6", "#eb6834"   # same colours as my fuel prices notebook
INK, MUTED, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def draw(conn, path=DEFAULT_CHART, weeks=52):
    rows = conn.execute("SELECT week, petrol, diesel FROM prices ORDER BY week DESC LIMIT ?", (weeks,)).fetchall()
    rows = rows[::-1]
    if len(rows) < 2:
        return None
    x = [date.fromisoformat(r["week"]) for r in rows]
    petrol = [r["petrol"] / 100 for r in rows]
    diesel = [r["diesel"] / 100 for r in rows]

    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=110, facecolor=BG)
    ax.set_facecolor(BG)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED, length=0)

    ax.plot(x, diesel, color=DIESEL, linewidth=2, label="Diesel")
    ax.plot(x, petrol, color=PETROL, linewidth=2, label="Petrol")
    for values in (diesel, petrol):  # label the latest value at the end of each line
        ax.annotate(f"{values[-1]:.1f}p", (x[-1], values[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=10, color=INK)

    ax.set_title(f"UK pump prices, last {len(rows)} weeks (latest: {x[-1]:%d %b %Y})",
                 loc="left", fontsize=13, fontweight="bold", color=INK)
    ax.set_ylabel("Pence per litre", color=MUTED)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(loc="upper left", frameon=False, labelcolor=MUTED)
    fig.text(0.01, 0.01, "Source: DESNZ weekly road fuel prices. Drawn automatically by the robot.",
             fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 0.97, 1))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path
