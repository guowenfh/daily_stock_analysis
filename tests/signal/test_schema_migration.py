"""Tests for signal table schema migration."""
from sqlalchemy import create_engine, text

from src.signal.models import ensure_signal_tables


def _columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]


def test_legacy_signal_tables_rebuilt_to_current_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE content_creators (
                id INTEGER PRIMARY KEY,
                platform VARCHAR(32),
                platform_uid VARCHAR(64),
                name VARCHAR(128),
                avatar_url TEXT,
                is_active BOOLEAN,
                last_fetched_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO content_creators
            (id, platform, platform_uid, name, avatar_url, is_active, last_fetched_at)
            VALUES (1, 'bilibili', 'u1', 'UP1', 'https://example.com/a.png', 1, '2026-05-01')
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE contents (
                id INTEGER PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                platform VARCHAR(32),
                platform_content_id VARCHAR(64),
                content_type VARCHAR(32),
                title TEXT,
                description TEXT,
                plain_text TEXT,
                subtitle TEXT,
                has_image BOOLEAN,
                cover_url TEXT,
                raw_json TEXT,
                processed BOOLEAN,
                process_error TEXT,
                publish_time DATETIME,
                fetched_at DATETIME,
                created_at DATETIME,
                display_type VARCHAR(32),
                text TEXT,
                url VARCHAR(1024),
                status VARCHAR(32)
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO contents
            (id, creator_id, platform, platform_content_id, content_type, title,
             plain_text, subtitle, has_image, cover_url, processed, process_error,
             publish_time, fetched_at, display_type, text, url, status)
            VALUES
            (10, 1, 'bilibili', 'BVold', 'video', '旧视频', '旧正文', '旧字幕',
             0, 'https://example.com/cover.jpg', 0, '旧错误',
             '2026-05-02', '2026-05-03', 'video_subtitle', '', '', 'pending_enrich')
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE content_media (
                id INTEGER PRIMARY KEY,
                content_id INTEGER NOT NULL,
                media_type VARCHAR(32),
                media_url TEXT,
                thumbnail_url TEXT,
                image_text TEXT,
                created_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO content_media
            (id, content_id, media_type, media_url, thumbnail_url, image_text)
            VALUES (20, 10, 'image', 'https://example.com/img.jpg',
                    'https://example.com/thumb.jpg', '图中文字')
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE content_transcripts (
                id INTEGER PRIMARY KEY,
                content_id INTEGER NOT NULL,
                platform VARCHAR(32),
                start_time REAL NOT NULL,
                end_time REAL,
                text TEXT NOT NULL,
                time_code VARCHAR(16),
                related_signals TEXT,
                source VARCHAR(32),
                quality VARCHAR(32),
                created_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO content_transcripts
            (id, content_id, platform, start_time, text, source, quality)
            VALUES (30, 10, 'bilibili', 12.5, '一段旧字幕', 'bilibili', 'unknown')
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE signal_events (
                id INTEGER PRIMARY KEY,
                event_date DATE NOT NULL,
                asset_name VARCHAR(128),
                asset_type VARCHAR(32),
                market VARCHAR(32),
                event_type VARCHAR(32),
                direction VARCHAR(32),
                strength FLOAT,
                score FLOAT,
                uploader_count INTEGER,
                mention_count INTEGER,
                evidence_json TEXT,
                created_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            INSERT INTO signal_events
            (id, event_date, asset_name, asset_type, market, direction,
             strength, uploader_count, mention_count)
            VALUES (40, '2026-05-02', '沪深300', 'index', 'A', 'opportunity', 2.5, 3, 5)
            """
        ))

    ensure_signal_tables(engine)

    with engine.connect() as conn:
        assert _columns(conn, "content_transcripts") == [
            "id", "content_id", "source", "text", "quality", "created_at",
        ]
        assert "plain_text" not in _columns(conn, "contents")
        assert "media_url" not in _columns(conn, "content_media")
        assert "uploader_count" not in _columns(conn, "signal_events")

        content = conn.execute(text("SELECT text, url, published_at FROM contents WHERE id = 10")).one()
        assert content.text == "旧正文"
        assert content.url == "https://example.com/cover.jpg"
        assert str(content.published_at).startswith("2026-05-02")

        media = conn.execute(text("SELECT url, ocr_text FROM content_media WHERE id = 20")).one()
        assert media.url == "https://example.com/img.jpg"
        assert media.ocr_text == "图中文字"

        transcript = conn.execute(text(
            "SELECT source, quality, text FROM content_transcripts WHERE id = 30"
        )).one()
        assert transcript.source == "platform"
        assert transcript.quality == "short"
        assert transcript.text == "一段旧字幕"

        event = conn.execute(text(
            "SELECT event_type, score, creator_count FROM signal_events WHERE id = 40"
        )).one()
        assert event.event_type == "opportunity"
        assert event.score == 2.5
        assert event.creator_count == 3


def test_signal_mentions_rebuilt_when_foreign_keys_point_to_legacy_tables():
    engine = create_engine("sqlite:///:memory:")
    ensure_signal_tables(engine)

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.execute(text("ALTER TABLE content_creators RENAME TO content_creators__legacy_signal_migration"))
        conn.execute(text("ALTER TABLE contents RENAME TO contents__legacy_signal_migration"))
        conn.execute(text(
            """
            CREATE TABLE content_creators (
                id INTEGER PRIMARY KEY,
                platform VARCHAR(32) NOT NULL,
                platform_uid VARCHAR(64) NOT NULL,
                name VARCHAR(128) NOT NULL,
                category VARCHAR(64),
                is_active BOOLEAN NOT NULL,
                manual_weight FLOAT NOT NULL,
                fetch_interval_min INTEGER,
                notes TEXT,
                last_fetch_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE contents (
                id INTEGER PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                platform VARCHAR(32) NOT NULL,
                platform_content_id VARCHAR(128) NOT NULL,
                content_type VARCHAR(32) NOT NULL,
                display_type VARCHAR(32) NOT NULL,
                title VARCHAR(512),
                text TEXT,
                url VARCHAR(1024),
                raw_json TEXT,
                status VARCHAR(32) NOT NULL,
                failure_stage VARCHAR(32),
                failure_reason TEXT,
                suggested_action VARCHAR(32),
                published_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(creator_id) REFERENCES content_creators(id)
            )
            """
        ))
        conn.execute(text("DROP TABLE content_creators__legacy_signal_migration"))
        conn.execute(text("DROP TABLE contents__legacy_signal_migration"))
        conn.execute(text("PRAGMA foreign_keys=ON"))

        legacy_refs = [
            row[2] for row in conn.execute(text("PRAGMA foreign_key_list(signal_mentions)"))
        ]
        assert "content_creators__legacy_signal_migration" in legacy_refs
        assert "contents__legacy_signal_migration" in legacy_refs

    ensure_signal_tables(engine)

    with engine.connect() as conn:
        refs = [row[2] for row in conn.execute(text("PRAGMA foreign_key_list(signal_mentions)"))]
        assert refs == ["content_creators", "contents"]
