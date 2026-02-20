from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from backend.models import PageDetail, PageSummary, PaginatedPages, SessionInfo, SessionSummary
from backend.report_store import ReportStore

SortKey = Literal[
    "risk_desc",
    "risk_asc",
    "score_desc",
    "score_asc",
    "issues_desc",
    "issues_asc",
    "url_asc",
    "url_desc",
]

app = FastAPI(title="AI SEO Auditor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ReportStore(Path(__file__).resolve().parent.parent)


def sort_pages(pages: list[PageSummary], sort: SortKey) -> list[PageSummary]:
    sort_map: dict[SortKey, tuple[str, bool]] = {
        "risk_desc": ("risk_index", True),
        "risk_asc": ("risk_index", False),
        "score_desc": ("overall_score", True),
        "score_asc": ("overall_score", False),
        "issues_desc": ("issues_count", True),
        "issues_asc": ("issues_count", False),
        "url_asc": ("url", False),
        "url_desc": ("url", True),
    }
    key, reverse = sort_map[sort]
    return sorted(pages, key=lambda p: getattr(p, key), reverse=reverse)


def apply_filters(
    pages: list[PageSummary],
    *,
    q: str | None,
    score_min: float,
    score_max: float,
    statuses: list[str] | None,
    issues_min: int,
) -> list[PageSummary]:
    filtered = pages
    if q:
        needle = q.lower()
        filtered = [p for p in filtered if needle in p.url.lower()]

    filtered = [p for p in filtered if score_min <= p.overall_score <= score_max]
    filtered = [p for p in filtered if p.issues_count >= issues_min]

    if statuses:
        status_set = set(statuses)
        filtered = [p for p in filtered if p.audit_status in status_set]

    return filtered


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sessions", response_model=list[SessionInfo])
def list_sessions() -> list[SessionInfo]:
    return store.list_sessions()


@app.get("/api/sessions/{session_id}/summary", response_model=SessionSummary)
def get_summary(session_id: str) -> SessionSummary:
    try:
        pages = store.load_pages(session_id)
        return store.load_summary(session_id, pages)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}/pages", response_model=PaginatedPages)
def get_pages(
    session_id: str,
    q: str | None = None,
    score_min: float = Query(0, ge=0, le=100),
    score_max: float = Query(100, ge=0, le=100),
    status: list[str] | None = Query(default=None),
    issues_min: int = Query(0, ge=0),
    sort: SortKey = Query("risk_desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> PaginatedPages:
    try:
        pages = [record.summary for record in store.load_pages(session_id)]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filtered = apply_filters(
        pages, q=q, score_min=score_min, score_max=score_max, statuses=status, issues_min=issues_min
    )
    ordered = sort_pages(filtered, sort)
    sliced = ordered[offset : offset + limit]
    return PaginatedPages(total=len(filtered), limit=limit, offset=offset, items=sliced)


@app.get("/api/sessions/{session_id}/pages/{page_id}", response_model=PageDetail)
def get_page(session_id: str, page_id: str) -> PageDetail:
    try:
        pages = store.load_pages(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    for page in pages:
        if page.page_id == page_id:
            return PageDetail(summary=page.summary, raw_data=page.raw_data)
    raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")


@app.get("/api/sessions/{session_id}/exports.csv")
def export_csv(
    session_id: str,
    q: str | None = None,
    score_min: float = Query(0, ge=0, le=100),
    score_max: float = Query(100, ge=0, le=100),
    status: list[str] | None = Query(default=None),
    issues_min: int = Query(0, ge=0),
    sort: SortKey = Query("risk_desc"),
) -> Response:
    try:
        pages = [record.summary for record in store.load_pages(session_id)]
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filtered = apply_filters(
        pages, q=q, score_min=score_min, score_max=score_max, statuses=status, issues_min=issues_min
    )
    ordered = sort_pages(filtered, sort)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(PageSummary.model_fields.keys()))
    writer.writeheader()
    for page in ordered:
        writer.writerow(page.model_dump())

    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=seo_audit_{session_id}.csv"},
    )


@app.get("/api/sessions/{session_id}/exports.json")
def export_json(
    session_id: str,
    q: str | None = None,
    score_min: float = Query(0, ge=0, le=100),
    score_max: float = Query(100, ge=0, le=100),
    status: list[str] | None = Query(default=None),
    issues_min: int = Query(0, ge=0),
    sort: SortKey = Query("risk_desc"),
) -> PlainTextResponse:
    try:
        pages = store.load_pages(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filtered_summaries = apply_filters(
        [record.summary for record in pages],
        q=q,
        score_min=score_min,
        score_max=score_max,
        statuses=status,
        issues_min=issues_min,
    )
    ordered = sort_pages(filtered_summaries, sort)
    id_set = {item.page_id for item in ordered}
    raw = [item.raw_data for item in pages if item.page_id in id_set]
    return PlainTextResponse(
        json.dumps(raw, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=seo_audit_{session_id}.json"},
    )

