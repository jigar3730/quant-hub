from quant_hub.engine.types import FactorResult


def make_factor_result(
    name: str,
    score: float,
    max_score: float,
    **details,
) -> FactorResult:
    return FactorResult(name=name, score=float(score), max_score=float(max_score), details=details)
