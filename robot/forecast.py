"""Forecasting the next few weeks of fuel prices, and checking honestly whether the forecast is any good.

Four ways of guessing next week's price, all scored on the same backtest:

1. Naive: next week will be the same as this week. The baseline anything clever has to beat.
2. Straight line: fit a line through the last 4 weeks and carry it on. (My first try. It lost to naive.)
3. Repeat: assume last week's change happens again. Simple, and already much better than naive.
4. Momentum: learn from the history how much of last week's change carries on into next week, using
   scikit-learn's LinearRegression on the weekly changes. About 77% does, not 100%. Over the last year it's level
   with "repeat" on petrol and ahead on diesel, and it's the best of the four over the whole history since 2019,
   so it's what the dashboard uses.
"""
from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import LinearRegression

LINE_WINDOW = 4   # weeks the straight line is fitted to (longer windows did even worse; a 2-week line is "repeat")
HORIZON = 4       # weeks ahead to forecast


def load_series(conn, fuel):
    """[(week, pence), ...] oldest first. fuel is 'petrol' or 'diesel'."""
    if fuel not in ("petrol", "diesel"):
        raise ValueError(f"Unknown fuel: {fuel}")
    rows = conn.execute(f"SELECT week, {fuel} FROM prices ORDER BY week").fetchall()
    return [(date.fromisoformat(r[0]), r[1] / 100) for r in rows]


# --- the four ways of guessing next week's price, each from a plain list of past prices ---

def naive_next(prices):
    return prices[-1]


def line_next(prices, window=LINE_WINDOW):
    recent = np.array(prices[-window:])
    x = np.arange(len(recent)).reshape(-1, 1)   # scikit-learn wants a 2D table of inputs
    model = LinearRegression().fit(x, recent)
    return float(model.predict(np.array([[len(recent)]]))[0])


def repeat_next(prices):
    return prices[-1] + (prices[-1] - prices[-2])


def fit_momentum(prices):
    """Learn how this week's change depends on last week's change. Returns the fitted model."""
    changes = np.diff(prices)                  # [p1-p0, p2-p1, ...]
    x = changes[:-1].reshape(-1, 1)            # last week's change...
    y = changes[1:]                            # ...and the change that followed it
    if len(y) < 2:
        raise ValueError("Need at least 4 weeks of prices to learn momentum")
    return LinearRegression().fit(x, y)


def momentum_next(prices, model=None):
    model = model or fit_momentum(prices)
    last_change = prices[-1] - prices[-2]
    return prices[-1] + float(model.predict(np.array([[last_change]]))[0])


def carry_over(series):
    """The share of one week's change that carries into the next (the momentum model's coefficient)."""
    return float(fit_momentum([p for _, p in series]).coef_[0])


# --- forecasting and backtesting ---

def forecast(series, horizon=HORIZON):
    """Momentum forecast for the next `horizon` weeks. Returns [(week, pence), ...].

    Each predicted week is fed back in to predict the one after it.
    """
    prices = [p for _, p in series]
    model = fit_momentum(prices)
    week = series[-1][0]
    result = []
    for _ in range(horizon):
        nxt = momentum_next(prices, model)
        prices.append(nxt)
        week += timedelta(weeks=1)
        result.append((week, round(nxt, 2)))
    return result


def backtest(series, weeks=52):
    """Replay the last `weeks` weeks. Each week is predicted using ONLY the weeks before it,
    so the models never see the answer. Returns the mean absolute error in pence for each method."""
    prices = [p for _, p in series]
    weeks = min(weeks, len(prices) - 6)
    if weeks < 1:
        raise ValueError("Not enough data to backtest")
    errors = {"naive": [], "line": [], "repeat": [], "momentum": []}
    for i in range(len(prices) - weeks, len(prices)):
        history, actual = prices[:i], prices[i]
        errors["naive"].append(abs(naive_next(history) - actual))
        errors["line"].append(abs(line_next(history) - actual))
        errors["repeat"].append(abs(repeat_next(history) - actual))
        errors["momentum"].append(abs(momentum_next(history) - actual))
    result = {name: round(sum(e) / weeks, 2) for name, e in errors.items()}
    result["weeks_tested"] = weeks
    return result
