def score_revenue(growth: float | None) -> float:
    if growth is None:
        return 0.0
    if growth >= 0.40:
        return 15.0
    if growth >= 0.25:
        return 12.0
    if growth >= 0.15:
        return 8.0
    if growth >= 0.05:
        return 4.0
    return 0.0


def score_eps(combined: float | None) -> float:
    if combined is None:
        return 0.0
    if combined >= 0.50:
        return 15.0
    if combined >= 0.30:
        return 12.0
    if combined >= 0.15:
        return 8.0
    if combined >= 0.0:
        return 4.0
    return 0.0
