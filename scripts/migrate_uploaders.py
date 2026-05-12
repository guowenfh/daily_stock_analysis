"""Migrate config/uploaders.json → content_creators table."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage import DatabaseManager
from src.signal.models import ContentCreator, ensure_signal_tables


def migrate():
    uploaders_path = Path("config/uploaders.json")
    if not uploaders_path.exists():
        print("config/uploaders.json not found, skipping migration")
        return

    with open(uploaders_path) as f:
        data = json.load(f)

    db = DatabaseManager.get_instance()
    ensure_signal_tables(db._engine)
    session = db.get_session()

    count = 0
    for group_key in ["key_uploaders", "filter_uploaders"]:
        for entry in data.get(group_key, []):
            uid = str(entry.get("uid", ""))
            if not uid:
                continue

            existing = session.query(ContentCreator).filter_by(
                platform="bilibili", platform_uid=uid,
            ).first()
            if existing:
                continue

            priority = entry.get("priority", 2)
            weight_map = {1: 1.5, 2: 1.0, 3: 0.7}

            creator = ContentCreator(
                platform="bilibili",
                platform_uid=uid,
                name=entry.get("name", f"uid_{uid}"),
                category=entry.get("category", ""),
                is_active=entry.get("is_active", True),
                manual_weight=weight_map.get(priority, 1.0),
                fetch_interval_min=entry.get("fetch_interval_min", 60),
            )
            session.add(creator)
            count += 1

    session.commit()
    session.close()
    print(f"Migrated {count} creators")


if __name__ == "__main__":
    migrate()
