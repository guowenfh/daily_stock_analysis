"""Collection and extraction quality tracking."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.signal.models import Content, ContentCreator

logger = logging.getLogger(__name__)


@dataclass
class QualityStats:
    total_contents: int = 0
    extracted_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    ignored_count: int = 0
    extraction_success_rate: float = 0.0
    active_creators: int = 0
    covered_creators: int = 0
    creator_coverage_rate: float = 0.0
    explainable_failures: int = 0
    failure_explainability_rate: float = 0.0


class QualityTracker:
    def __init__(self, session: Session):
        self.session = session

    def compute_stats(self, since: Optional[datetime] = None) -> QualityStats:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        stats = QualityStats()

        status_counts = (
            self.session.query(Content.status, func.count(Content.id))
            .filter(Content.created_at >= since)
            .group_by(Content.status)
            .all()
        )
        status_map = dict(status_counts)

        stats.total_contents = sum(status_map.values())
        stats.extracted_count = status_map.get("extracted", 0) + status_map.get("low_confidence", 0)
        stats.failed_count = status_map.get("failed", 0)
        stats.ignored_count = status_map.get("ignored", 0)
        stats.pending_count = (
            status_map.get("collected", 0)
            + status_map.get("pending_enrich", 0)
            + status_map.get("pending_extract", 0)
        )

        processable = stats.total_contents - stats.ignored_count
        if processable > 0:
            stats.extraction_success_rate = stats.extracted_count / processable

        stats.active_creators = self.session.query(ContentCreator).filter(
            ContentCreator.is_active == True,
        ).count()

        stats.covered_creators = (
            self.session.query(func.count(func.distinct(Content.creator_id)))
            .filter(Content.created_at >= since)
            .scalar()
        ) or 0

        if stats.active_creators > 0:
            stats.creator_coverage_rate = stats.covered_creators / stats.active_creators

        if stats.failed_count > 0:
            stats.explainable_failures = (
                self.session.query(Content)
                .filter(
                    Content.status == "failed",
                    Content.created_at >= since,
                    Content.failure_stage.isnot(None),
                    Content.failure_reason.isnot(None),
                )
                .count()
            )
            stats.failure_explainability_rate = stats.explainable_failures / stats.failed_count

        return stats

    def get_funnel(self, since: Optional[datetime] = None) -> dict[str, int]:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        rows = (
            self.session.query(Content.status, func.count(Content.id))
            .filter(Content.created_at >= since)
            .group_by(Content.status)
            .all()
        )
        return dict(rows)

    def get_failure_reasons(self, since: Optional[datetime] = None, limit: int = 20) -> list[dict]:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        rows = (
            self.session.query(
                Content.failure_stage,
                Content.failure_reason,
                func.count(Content.id).label("count"),
            )
            .filter(Content.status == "failed", Content.created_at >= since)
            .group_by(Content.failure_stage, Content.failure_reason)
            .order_by(func.count(Content.id).desc())
            .limit(limit)
            .all()
        )
        return [
            {"stage": r[0], "reason": r[1], "count": r[2]}
            for r in rows
        ]

    def get_creator_stats(self, since: Optional[datetime] = None) -> list[dict]:
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        creators = self.session.query(ContentCreator).filter(
            ContentCreator.is_active == True,
        ).all()

        result = []
        for c in creators:
            total = self.session.query(Content).filter(
                Content.creator_id == c.id,
                Content.created_at >= since,
            ).count()
            extracted = self.session.query(Content).filter(
                Content.creator_id == c.id,
                Content.status.in_(["extracted", "low_confidence"]),
                Content.created_at >= since,
            ).count()
            failed = self.session.query(Content).filter(
                Content.creator_id == c.id,
                Content.status == "failed",
                Content.created_at >= since,
            ).count()
            result.append({
                "creator_id": c.id,
                "name": c.name,
                "total": total,
                "extracted": extracted,
                "failed": failed,
                "success_rate": extracted / total if total > 0 else 0.0,
                "last_fetch_at": c.last_fetch_at.isoformat() if c.last_fetch_at else None,
            })

        return result
