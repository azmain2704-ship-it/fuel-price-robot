from datetime import date, timedelta

import pytest

from robot import forecast


def make_series(prices, start=date(2026, 1, 5)):
    return [(start + timedelta(weeks=i), p) for i, p in enumerate(prices)]


def test_naive_guess_is_last_weeks_price():
    assert forecast.naive_next([150.0, 152.0, 151.0]) == 151.0


def test_straight_line_carries_a_steady_rise_forward():
    assert forecast.line_next([150.0, 151.0, 152.0, 153.0]) == pytest.approx(154.0)


def test_repeat_assumes_last_weeks_change_happens_again():
    assert forecast.repeat_next([150.0, 151.0, 153.0]) == pytest.approx(155.0)


def test_momentum_learns_a_steady_rise():
    # Prices rising exactly 1p a week, so every change is +1 and the next one should be too
    prices = [150.0 + i for i in range(10)]
    assert forecast.momentum_next(prices) == pytest.approx(160.0)


def test_momentum_learns_how_much_of_a_change_carries_on():
    # Each change is exactly half the one before, so the model should learn a carry-over of 0.5
    changes = [16 * 0.5 ** i for i in range(8)]
    prices = [100.0]
    for c in changes:
        prices.append(prices[-1] + c)
    series = make_series(prices)
    assert forecast.carry_over(series) == pytest.approx(0.5)


def test_forecast_weeks_follow_on_from_the_last_week():
    series = make_series([150.0 + i for i in range(10)])
    result = forecast.forecast(series, horizon=3)
    last = series[-1][0]
    assert [w for w, _ in result] == [last + timedelta(weeks=n) for n in (1, 2, 3)]
    assert [p for _, p in result] == pytest.approx([160.0, 161.0, 162.0])


def test_flat_prices_give_a_flat_forecast():
    series = make_series([140.5] * 12)
    assert all(p == pytest.approx(140.5) for _, p in forecast.forecast(series))


def test_too_little_data_is_refused():
    with pytest.raises(ValueError):
        forecast.forecast(make_series([150.0, 151.0, 152.0]))


def test_backtest_never_sees_the_answer():
    # A sudden jump in the final week can't be predicted from the weeks before it,
    # so every method should be wrong by the full 30p
    series = make_series([100.0] * 20 + [130.0])
    result = forecast.backtest(series, weeks=1)
    for method in ("naive", "line", "repeat", "momentum"):
        assert result[method] == pytest.approx(30)


def test_momentum_beats_naive_on_a_steady_trend():
    series = make_series([100.0 + 2 * i for i in range(30)])
    result = forecast.backtest(series, weeks=10)
    assert result["momentum"] == pytest.approx(0)
    assert result["naive"] == pytest.approx(2)


def test_unknown_fuel_is_refused():
    with pytest.raises(ValueError):
        forecast.load_series(None, "kerosene")
