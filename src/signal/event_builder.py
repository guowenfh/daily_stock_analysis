"""Aggregate signal mentions into single-asset events."""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from src.signal.models import SignalMention, SignalEvent, ContentCreator, Content

logger = logging.getLogger(__name__)


@dataclass
class EventBuildResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


class SignalEventBuilder:
    def __init__(self, session: Session):
        self.session = session

    def build(self, target_date: date) -> EventBuildResult:
        result = EventBuildResult()

        # created_at uses datetime.utcnow (naive UTC). Bounds are UTC midnight for target_date.
        day_start = datetime(target_date.year, target_date.month, target_date.day)
        day_end = day_start + timedelta(days=1)

        mentions = (
            self.session.query(SignalMention)
            .join(Content, SignalMention.content_id == Content.id)
            .filter(
                Content.status.in_(["extracted", "low_confidence"]),
                SignalMention.created_at >= day_start,
                SignalMention.created_at < day_end,
            )
            .all()
        )

        grouped = defaultdict(list)
        for m in mentions:
            key = (m.asset_name, m.asset_type)
            grouped[key].append(m)

        for (asset_name, asset_type), group in grouped.items():
            try:
                self._build_event(asset_name, asset_type, group, target_date, result)
            except Exception as e:
                result.errors.append(f"Error building event for {asset_name}: {e}")
                logger.exception("Failed to build event for %s", asset_name)

        self.session.commit()
        return result

    def _build_event(
        self,
        asset_name: str,
        asset_type: str,
        mentions: list[SignalMention],
        target_date: date,
        result: EventBuildResult,
    ):
        bullish = [m for m in mentions if m.sentiment == "bullish"]
        bearish = [m for m in mentions if m.sentiment == "bearish"]
        neutral = [m for m in mentions if m.sentiment == "neutral"]

        creator_ids = set(m.creator_id for m in mentions)
        creator_count = len(creator_ids)

        creators = {
            c.id: c for c in
            self.session.query(ContentCreator).filter(
                ContentCreator.id.in_(creator_ids)
            ).all()
        }

        event_type = self._classify_event(
            bullish, bearish, neutral, creators, mentions,
        )
        score = self._compute_score(mentions, creators)

        top_creator = max(
            creators.values(),
            key=lambda c: c.manual_weight,
            default=None
        )

        asset_code = next((m.asset_code for m in mentions if m.asset_code), None)
        market = mentions[0].market if mentions else "unknown"

        evidence = self._build_evidence(mentions, creators)

        existing = self.session.query(SignalEvent).filter_by(
            asset_name=asset_name, asset_type=asset_type, event_date=target_date,
        ).first()

        if existing:
            existing.event_type = event_type
            existing.score = score
            existing.bullish_count = len(bullish)
            existing.bearish_count = len(bearish)
            existing.neutral_count = len(neutral)
            existing.creator_count = creator_count
            existing.mention_count = len(mentions)
            existing.top_creator_name = top_creator.name if top_creator else None
            existing.set_evidence(evidence)
            existing.asset_code = asset_code
            result.updated += 1
        else:
            ev = SignalEvent(
                asset_name=asset_name,
                asset_code=asset_code,
                asset_type=asset_type,
                market=market,
                event_type=event_type,
                event_date=target_date,
                score=score,
                bullish_count=len(bullish),
                bearish_count=len(bearish),
                neutral_count=len(neutral),
                creator_count=creator_count,
                mention_count=len(mentions),
                top_creator_name=top_creator.name if top_creator else None,
            )
            ev.set_evidence(evidence)
            self.session.add(ev)
            result.created += 1

    def _classify_event(
        self,
        bullish: list, bearish: list, neutral: list,
        creators: dict, all_mentions: list,
    ) -> str:
        total = len(bullish) + len(bearish) + len(neutral)
        if total == 0:
            return "watch"

        bull_ratio = len(bullish) / total
        bear_ratio = len(bearish) / total

        bull_creators = set(m.creator_id for m in bullish)
        bear_creators = set(m.creator_id for m in bearish)

        has_high_weight_bull = any(
            creators.get(cid) and creators[cid].manual_weight >= 1.5
            for cid in bull_creators
        )
        has_high_weight_bear = any(
            creators.get(cid) and creators[cid].manual_weight >= 1.5
            for cid in bear_creators
        )

        if len(bull_creators) >= 2 and len(bear_creators) >= 2:
            return "conflict"

        if bull_ratio >= 0.6 and len(bull_creators) >= 2:
            return "opportunity"
        if has_high_weight_bull and bull_ratio >= 0.5:
            return "opportunity"

        if bear_ratio >= 0.6 and len(bear_creators) >= 2:
            return "risk"
        if has_high_weight_bear and bear_ratio >= 0.5:
            return "risk"

        return "watch"

    def _compute_score(self, mentions: list[SignalMention], creators: dict) -> float:
        if not mentions:
            return 0.0

        total = len(mentions)

        bullish = sum(1 for m in mentions if m.sentiment == "bullish")
        bearish = sum(1 for m in mentions if m.sentiment == "bearish")
        sentiment_strength = abs(bullish - bearish) / total
        sentiment_score = sentiment_strength * 100

        avg_confidence = sum(m.confidence for m in mentions) / total
        confidence_score = avg_confidence * 100

        creator_ids = set(m.creator_id for m in mentions)
        max_weight = max(
            (creators.get(cid, None) for cid in creator_ids),
            key=lambda c: c.manual_weight if c else 0,
            default=None,
        )
        weight_score = min(len(creator_ids) * 20, 60)
        if max_weight and max_weight.manual_weight >= 1.5:
            weight_score = min(weight_score + 30, 100)

        advice_count = sum(1 for m in mentions if m.trade_advice)
        advice_score = (advice_count / total) * 100

        primary_count = sum(1 for m in mentions if m.is_primary)
        primary_score = (primary_count / total) * 100

        final = (
            sentiment_score * 0.30
            + confidence_score * 0.20
            + weight_score * 0.30
            + advice_score * 0.10
            + primary_score * 0.10
        )
        return round(min(max(final, 0), 100), 1)

    def _build_evidence(self, mentions: list[SignalMention], creators: dict) -> list[dict]:
        evidence = []
        for m in mentions:
            creator = creators.get(m.creator_id)
            content = self.session.get(Content, m.content_id)
            evidence.append({
                "mention_id": m.id,
                "content_id": m.content_id,
                "creator_id": m.creator_id,
                "creator_name": creator.name if creator else "unknown",
                "creator_weight": creator.manual_weight if creator else 1.0,
                "content_title": content.title if content else "",
                "content_type": content.content_type if content else "",
                "display_type": content.display_type if content else "",
                "sentiment": m.sentiment,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "trade_advice": m.trade_advice,
                "source_url": content.url if content else "",
                "published_at": content.published_at.isoformat() if content and content.published_at else None,
            })
        return evidence
