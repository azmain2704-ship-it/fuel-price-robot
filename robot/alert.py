"""The alert: has petrol or diesel moved more than 5% in a week?"""
from robot.source import format_pence, week_label

THRESHOLD = 5.0  # percent


def percent_change(old, new):
    return (new - old) * 100 / old


def check_for_jumps(latest, previous, threshold=THRESHOLD):
    """Compare the two most recent weeks. Returns a list of (fuel, old, new, change%) for big moves."""
    jumps = []
    for fuel in ("petrol", "diesel"):
        old, new = previous[fuel], latest[fuel]
        change = percent_change(old, new)
        if abs(change) > threshold:
            jumps.append((fuel, old, new, change))
    return jumps


def alert_text(latest, previous, jumps, owner=None, test=False):
    """First line is the issue title, the rest is the body."""
    if test:
        title = "Test alert from the fuel price robot"
        intro = "This is a test, triggered by hand, to check the alert reaches you. Prices didn't really jump."
    else:
        moves = ", ".join(f"{fuel} {'up' if change > 0 else 'down'} {abs(change):.1f}%" for fuel, _, _, change in jumps)
        title = f"Fuel price alert: {moves} in the week to {week_label(latest['week'])}"
        intro = f"Prices moved more than 5% between {week_label(previous['week'])} and {week_label(latest['week'])}."

    lines = [title, "", intro, "", "| Fuel | Previous week | This week | Change |", "|---|---|---|---|"]
    for fuel in ("petrol", "diesel"):
        old, new = previous[fuel], latest[fuel]
        lines.append(f"| {fuel.title()} | {format_pence(old)} | {format_pence(new)} | {percent_change(old, new):+.1f}% |")
    lines += ["", "Source: DESNZ weekly road fuel prices, via the GOV.UK Content API."]
    if owner:
        lines += ["", f"@{owner}"]  # mentioning the owner makes GitHub send them an email
    return "\n".join(lines) + "\n"
