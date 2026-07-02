"""Digest email preview for the Streamlit dashboard."""

from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from quant_hub.digest.analytics import build_daily_payload, build_weekly_payload
from quant_hub.digest import policy as P
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.notify.digest_email import build_daily_digest_email, build_weekly_digest_email


def digest_job_name(digest_kind: str, scan_date: date) -> str:
    if digest_kind == "weekly":
        return f"digest-weekly-{scan_date.isoformat()}"
    return f"digest-daily-{scan_date.isoformat()}"


def build_digest_preview(
    repo: ScanRepository,
    *,
    digest_kind: str,
    scan_date: date,
) -> dict[str, Any]:
    """Build subject, HTML, and payload for a digest preview."""
    if digest_kind == "weekly":
        payload = build_weekly_payload(repo, lynch_date=scan_date)
        subject, html = build_weekly_digest_email(payload)
    else:
        payload = build_daily_payload(repo, scan_date=scan_date)
        subject, html = build_daily_digest_email(payload)
    return {
        "digest_kind": digest_kind,
        "scan_date": scan_date,
        "subject": subject,
        "html": html,
        "payload": payload,
        "job_name": digest_job_name(digest_kind, scan_date),
    }


def _summary_metrics(digest_kind: str, payload: dict) -> list[tuple[str, str]]:
    if digest_kind == "weekly":
        return [
            ("Triple alignment", str(len(payload.get("triple_alignment") or []))),
            ("Swing highlights", str(len(payload.get("swing_highlights") or []))),
            ("Lynch picks", str(len(payload.get("lynch_top") or []))),
        ]
    tier1 = len(payload.get("tier1") or [])
    tier2 = len(payload.get("tier2") or [])
    return [
        ("High conviction", str(tier1)),
        ("Watchlist", str(tier2)),
        ("New today", str(len(payload.get("new_entrants") or []))),
    ]


def render_digest_preview_tab(
    repo: ScanRepository,
    job_repo: JobRunRepository,
    *,
    digest_kind: str,
    scan_date: date | None,
) -> None:
    st.markdown(
        """
        <div class="scan-header">
            <h1>Digest Email Preview</h1>
            <p>Live preview of scheduled daily and weekly digest emails — same HTML as inbox delivery.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if scan_date is None:
        st.warning("No scan date available for this digest type yet.")
        st.info(
            "Run `quant-daily --universe sp500_index` for daily digests, or "
            "`quant-lynch-all` / `quant-swing-all` for weekly content."
        )
        return

    try:
        preview = build_digest_preview(repo, digest_kind=digest_kind, scan_date=scan_date)
    except RuntimeError as exc:
        st.error(str(exc))
        return

    payload = preview["payload"]
    sent = job_repo.job_succeeded(preview["job_name"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Digest date", str(scan_date))
    c2.metric("Email status", "Sent" if sent else "Not sent")
    metrics = _summary_metrics(digest_kind, payload)
    c3.metric(metrics[0][0], metrics[0][1])
    c4.metric(metrics[1][0], metrics[1][1])

    st.markdown(f"**Subject:** `{preview['subject']}`")
    st.caption(
        f"Policy: {P.DAILY_BREAKOUT_UNIVERSE} breakout"
        + (" · cross-strategy weekly rollup" if digest_kind == "weekly" else "")
    )

    tab_preview, tab_payload, tab_cli = st.tabs(["Email preview", "Payload JSON", "CLI"])

    with tab_preview:
        components.html(preview["html"], height=1100, scrolling=True)

    with tab_payload:
        st.json(payload)

    with tab_cli:
        if digest_kind == "weekly":
            st.code(
                f"quant-digest weekly --date {scan_date.isoformat()} --no-email\n"
                f"quant-digest weekly --date {scan_date.isoformat()} --force",
                language="bash",
            )
        else:
            st.code(
                f"quant-digest daily --date {scan_date.isoformat()} --no-email\n"
                f"quant-digest daily --date {scan_date.isoformat()} --force",
                language="bash",
            )
        st.caption("Use `--force` to resend after previewing. Omit `--no-email` to deliver.")
