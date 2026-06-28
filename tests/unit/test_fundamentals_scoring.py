from quant_hub.scoring.fundamentals import score_eps, score_revenue


def test_score_revenue_missing_not_confused_with_zero():
    scored = score_revenue(None, status="MISSING")
    assert scored.score == 0.0
    assert scored.status == "MISSING"
    assert scored.value is None


def test_score_revenue_negative_status():
    scored = score_revenue(-0.05, status="OK")
    assert scored.status == "NEGATIVE"
    assert scored.score == 0.0


def test_score_eps_capped_still_scores():
    scored = score_eps(3.0, status="CAPPED")
    assert scored.status == "CAPPED"
    assert scored.score == 15.0


def test_score_eps_missing():
    scored = score_eps(None, status="NOT_APPLICABLE")
    assert scored.status == "NOT_APPLICABLE"
    assert scored.value is None
