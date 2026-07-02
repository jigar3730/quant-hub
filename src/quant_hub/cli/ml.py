"""quant-ml — labels, feature export, model training and evaluation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

from quant_hub.application.ml_cache_service import MLCacheService
from quant_hub.application.ml_evaluate_service import MLEvaluateService
from quant_hub.application.ml_export_service import MLExportService
from quant_hub.application.ml_label_service import MLLabelService
from quant_hub.application.ml_train_service import MLTrainService
from quant_hub.config import DEFAULT_LABEL_HORIZONS, PRIMARY_INDEX_UNIVERSE
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _parse_horizons(value: str) -> tuple[int, ...]:
    return tuple(int(h.strip()) for h in value.split(",") if h.strip())


def _cmd_label(args: argparse.Namespace) -> int:
    service = MLLabelService()
    stats = service.run(
        run_id=args.run_id,
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        horizons=args.horizons,
        return_threshold_pct=args.threshold,
    )
    print(stats.summary())
    return 0 if stats.runs_processed > 0 or args.run_id else 1


def _cmd_export_features(args: argparse.Namespace) -> int:
    service = MLExportService()
    stats = service.run(
        run_id=args.run_id,
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        horizon_days=args.horizon,
        include_labels=not args.no_labels,
        per_run_files=args.per_run,
    )
    print(stats.summary())
    return 0 if stats.rows_written > 0 else 1


def _cmd_status() -> int:
    repo = OutcomesRepository()
    total = repo.count_total()
    by_status = repo.count_by_status()
    print(f"signal_outcomes: {total}")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")
    return 0


def _cmd_warm_cache(args: argparse.Namespace) -> int:
    service = MLCacheService()
    stats = service.warm_daily_prices(
        universe_id=args.universe,
        force_refresh=args.force_refresh,
    )
    print(stats.summary())
    return 0 if stats.tickers_requested > 0 else 1


def _cmd_train(args: argparse.Namespace) -> int:
    service = MLTrainService()
    stats = service.run(
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        horizon_days=args.horizon,
        split_date=args.split_date,
        name=args.name,
        setups_only=not args.all_tiers,
        top_k=args.top_k,
    )
    print(stats.summary())
    if stats.feature_importance:
        top = sorted(stats.feature_importance.items(), key=lambda x: -x[1])[:5]
        print("top features:", ", ".join(f"{k}={v:.0f}" for k, v in top))
    return 0 if stats.model_id else 1


def _cmd_evaluate(args: argparse.Namespace) -> int:
    service = MLEvaluateService()
    stats = service.run(
        model_id=args.model_id,
        artifact_path=args.artifact_path,
        since=args.since,
        until=args.until,
        walk_forward=args.walk_forward,
        train_weeks=args.train_weeks,
        test_weeks=args.test_weeks,
        top_k=args.top_k,
    )
    print(stats.summary())
    for line in stats.fold_summaries:
        print(f"  {line}")
    if args.json:
        print(json.dumps(stats.metrics, indent=2))
    return 0 if stats.metrics and "error" not in stats.metrics else 1


def _cmd_models(args: argparse.Namespace) -> int:
    repo = MlModelsRepository()
    rows = repo.list_models(
        strategy_id=args.strategy,
        universe_id=args.universe,
        status=args.status,
        limit=args.limit,
    )
    if not rows:
        print("No models registered")
        return 0
    for row in rows:
        holdout = (row.get("metrics") or {}).get("holdout", {})
        auc = holdout.get("auc") if isinstance(holdout, dict) else None
        auc_str = f" auc={auc:.4f}" if auc is not None else ""
        print(
            f"id={row['id']} {row['name']} {row['strategy_id']}/{row['universe_id']} "
            f"h{row['horizon_days']} {row['status']}{auc_str} "
            f"train={row.get('train_since')}..{row.get('train_until')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ML pipeline — labels, features, training, and evaluation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    label = sub.add_parser("label", help="Compute forward-return labels for scan runs")
    label.add_argument("--run-id", type=int, help="Label a single scan run by id")
    label.add_argument("--strategy", choices=("breakout", "swing", "lynch"))
    label.add_argument("--universe", help=f"Universe id filter (e.g. {PRIMARY_INDEX_UNIVERSE})")
    label.add_argument("--since", type=date.fromisoformat)
    label.add_argument("--until", type=date.fromisoformat)
    label.add_argument(
        "--horizons",
        type=_parse_horizons,
        default=DEFAULT_LABEL_HORIZONS,
        help=f"Comma-separated horizons (default: {','.join(map(str, DEFAULT_LABEL_HORIZONS))})",
    )
    label.add_argument(
        "--threshold",
        type=float,
        default=2.0,
        help="Binary label threshold: forward return >= threshold pct",
    )

    export = sub.add_parser("export-features", help="Export flattened features to Parquet")
    export.add_argument("--run-id", type=int)
    export.add_argument("--strategy", choices=("breakout", "swing", "lynch"))
    export.add_argument("--universe")
    export.add_argument("--since", type=date.fromisoformat)
    export.add_argument("--until", type=date.fromisoformat)
    export.add_argument(
        "--horizon",
        type=int,
        help="Label horizon to join (default: 10 when labels included)",
    )
    export.add_argument("--no-labels", action="store_true", help="Export features only")
    export.add_argument(
        "--per-run",
        action="store_true",
        help="Write one Parquet file per scan run instead of a combined export",
    )

    sub.add_parser("status", help="Show signal_outcomes counts")

    warm = sub.add_parser("warm-cache", help="Download extended daily OHLCV for labeling")
    warm.add_argument(
        "--universe",
        default=PRIMARY_INDEX_UNIVERSE,
        help=f"Universe id (default: {PRIMARY_INDEX_UNIVERSE})",
    )
    warm.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass parquet cache and re-fetch from yfinance",
    )

    train = sub.add_parser("train", help="Train a LightGBM classifier on labeled setups")
    train.add_argument("--strategy", choices=("breakout", "swing", "lynch"), default="swing")
    train.add_argument("--universe", default=PRIMARY_INDEX_UNIVERSE)
    train.add_argument("--since", type=date.fromisoformat, required=True)
    train.add_argument("--until", type=date.fromisoformat)
    train.add_argument("--horizon", type=int, default=10, help="Label horizon days (default: 10)")
    train.add_argument(
        "--split-date",
        type=date.fromisoformat,
        help="Holdout split: train before this date, eval on/after (default: last 26 weeks)",
    )
    train.add_argument("--name", help="Model registry name (default: auto-generated)")
    train.add_argument(
        "--all-tiers",
        action="store_true",
        help="Include all tiers, not just SETUP_LONG/SETUP_SHORT",
    )
    train.add_argument("--top-k", type=int, default=5, help="Top-K for holdout return metric")

    evaluate = sub.add_parser("evaluate", help="Evaluate a registered model")
    evaluate.add_argument("--model-id", type=int, help="Registry model id")
    evaluate.add_argument("--artifact-path", help="Path to model artifact directory")
    evaluate.add_argument("--since", type=date.fromisoformat)
    evaluate.add_argument("--until", type=date.fromisoformat)
    evaluate.add_argument(
        "--walk-forward",
        action="store_true",
        help="Rolling walk-forward evaluation across held-out weeks",
    )
    evaluate.add_argument("--train-weeks", type=int, default=52)
    evaluate.add_argument("--test-weeks", type=int, default=13)
    evaluate.add_argument("--top-k", type=int, default=5)
    evaluate.add_argument("--json", action="store_true", help="Print metrics JSON")

    models = sub.add_parser("models", help="List registered models")
    models.add_argument("--strategy", choices=("breakout", "swing", "lynch"))
    models.add_argument("--universe")
    models.add_argument("--status", choices=("active", "archived"))
    models.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(argv)
    setup_logging("ml.log")

    if not ping():
        print("Database unreachable", file=sys.stderr)
        return 1

    if args.command == "label":
        return _cmd_label(args)
    if args.command == "export-features":
        return _cmd_export_features(args)
    if args.command == "status":
        return _cmd_status()
    if args.command == "warm-cache":
        return _cmd_warm_cache(args)
    if args.command == "train":
        return _cmd_train(args)
    if args.command == "evaluate":
        return _cmd_evaluate(args)
    if args.command == "models":
        return _cmd_models(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
