"""Bilibili content collector using bili CLI."""
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import yaml

from src.signal.models import ContentCreator, Content, ContentMedia

logger = logging.getLogger(__name__)

CONTENT_TYPE_MAP = {
    "MAJOR_TYPE_ARCHIVE": "video",
    "MAJOR_TYPE_COMMON": "article",
    "MAJOR_TYPE_OPUS": "article",
    "MAJOR_TYPE_DRAW": "image",
}

DISPLAY_TYPE_MAP = {
    "video": "video_subtitle",
    "image": "image_text",
    "article": "text",
    "dynamic": "text",
    "forward": "text",
}


@dataclass
class CollectResult:
    new: int = 0
    duplicate: int = 0
    skipped: int = 0
    failed: int = 0
    pages_fetched: int = 0
    errors: list[str] = field(default_factory=list)


class BilibiliCollector:
    def __init__(self, session):
        self.session = session

    def fetch_feed(
        self,
        max_pages: int = 3,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> CollectResult:
        """Fetch feed with automatic pagination.

        Paginates through the feed using offset cursors until one of:
        - All items on a page are duplicates (caught up)
        - Reached max_pages
        - No more items or no next_offset
        """
        result = CollectResult()
        creators = self._load_active_creators()
        if not creators:
            logger.info("No active creators, skipping feed collection")
            return result

        creator_by_uid = {c.platform_uid: c for c in creators}
        creator_by_name = {c.name: c for c in creators}

        offset: Optional[str] = None
        for page in range(max_pages):
            raw_items, next_offset = self._call_bili_feed_page(
                offset=offset,
                max_retries=max_retries,
                timeout=timeout,
            )
            result.pages_fetched += 1

            if raw_items is None:
                result.failed += 1
                result.errors.append(
                    f"bili feed failed on page {page + 1}"
                )
                break

            if not raw_items:
                logger.info("Empty feed page %d, stopping", page + 1)
                break

            new_before = result.new
            for item in raw_items:
                try:
                    self._process_item(
                        item, creator_by_uid, creator_by_name, result
                    )
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Error processing item: {e}")
                    logger.exception("Failed to process feed item")

            self.session.commit()

            page_new = result.new - new_before
            if page_new == 0:
                logger.info(
                    "Page %d: all items duplicated, stopping pagination",
                    page + 1,
                )
                break

            logger.info(
                "Page %d: %d new items collected", page + 1, page_new
            )

            if not next_offset:
                break
            offset = next_offset

        return result

    def _call_bili_feed_page(
        self,
        offset: Optional[str],
        max_retries: int,
        timeout: int,
    ) -> tuple[Optional[list], Optional[str]]:
        """Call bili feed for a single page, return (items, next_offset)."""
        cmd = ["bili", "feed", "--yaml"]
        if offset:
            cmd.extend(["--offset", offset])

        for attempt in range(max_retries):
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if proc.returncode != 0:
                    logger.warning(
                        "bili feed failed (attempt %d): %s",
                        attempt + 1,
                        proc.stderr[:200],
                    )
                    continue

                data = yaml.safe_load(proc.stdout)
                return self._parse_feed_response(data)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "bili feed timed out (attempt %d)", attempt + 1
                )
            except Exception as e:
                logger.warning(
                    "bili feed error (attempt %d): %s", attempt + 1, e
                )
        return None, None

    def _parse_feed_response(
        self, data
    ) -> tuple[Optional[list], Optional[str]]:
        """Extract items list and next_offset from feed response."""
        if isinstance(data, list):
            return data, None
        if isinstance(data, dict):
            inner = data.get("data", data)
            if isinstance(inner, dict):
                items = inner.get("items", [])
                next_offset = inner.get("next_offset") or inner.get(
                    "offset"
                )
                if isinstance(next_offset, (int, float)):
                    next_offset = str(next_offset)
                return items if items else [], next_offset
            if "items" in data:
                return data["items"], data.get("next_offset")
        return data if data else [], None

    def _load_active_creators(self) -> list[ContentCreator]:
        return (
            self.session.query(ContentCreator)
            .filter(
                ContentCreator.is_active == True,
                ContentCreator.platform == "bilibili",
            )
            .all()
        )

    def _match_creator(
        self,
        uid: str,
        name: str,
        by_uid: dict,
        by_name: dict,
    ) -> Optional[ContentCreator]:
        if uid and uid in by_uid:
            return by_uid[uid]
        if name and name in by_name:
            return by_name[name]
        return None

    def _process_item(
        self,
        item: dict,
        by_uid: dict,
        by_name: dict,
        result: CollectResult,
    ):
        author = item.get("author", {}) or {}
        uid = str(author.get("mid", "") or item.get("uid", ""))
        name = author.get("name", "") or item.get("author_name", "")

        creator = self._match_creator(uid, name, by_uid, by_name)
        if creator is None:
            result.skipped += 1
            return

        dynamic_id = str(
            item.get("id", "") or item.get("dynamic_id", "")
        )
        bvid = item.get("bvid", "")
        platform_content_id = bvid or dynamic_id
        if not platform_content_id:
            result.skipped += 1
            return

        existing = (
            self.session.query(Content)
            .filter_by(
                platform="bilibili",
                platform_content_id=platform_content_id,
            )
            .first()
        )
        if existing:
            result.duplicate += 1
            return

        major_type = item.get("type", "") or item.get("major_type", "")
        content_type = CONTENT_TYPE_MAP.get(major_type, "dynamic")
        display_type = DISPLAY_TYPE_MAP.get(content_type, "text")

        title = item.get("title", "")
        text = item.get("text", "") or item.get("desc", "")
        url = item.get("url", "")
        if bvid and not url:
            url = f"https://www.bilibili.com/video/{bvid}"

        published_at = None
        pub_ts = item.get("pub_ts") or item.get("publish_time")
        if pub_ts:
            try:
                published_at = datetime.fromtimestamp(int(pub_ts))
            except (ValueError, TypeError, OSError):
                pass
        if published_at is None:
            pub_at = item.get("published_at", "")
            if pub_at:
                try:
                    published_at = datetime.fromisoformat(pub_at)
                except (ValueError, TypeError):
                    pass

        initial_status = (
            "pending_enrich" if display_type == "video_subtitle" else "pending_extract"
        )

        content = Content(
            creator_id=creator.id,
            platform="bilibili",
            platform_content_id=platform_content_id,
            content_type=content_type,
            display_type=display_type,
            title=title,
            text=text,
            url=url,
            raw_json=json.dumps(item, ensure_ascii=False),
            status=initial_status,
            published_at=published_at,
        )
        self.session.add(content)
        self.session.flush()

        images = item.get("images", []) or item.get("pics", []) or []
        for img_url in images:
            if isinstance(img_url, str):
                media = ContentMedia(
                    content_id=content.id,
                    media_type="image",
                    url=img_url,
                )
                self.session.add(media)

        if images and display_type == "text":
            content.display_type = "image_text"
            content.status = "pending_extract"

        creator.last_fetch_at = datetime.utcnow()
        result.new += 1
