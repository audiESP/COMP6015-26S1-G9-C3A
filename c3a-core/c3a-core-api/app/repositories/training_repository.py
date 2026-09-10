"""Database-backed training material repository."""

from __future__ import annotations

import os
from typing import Any

from app.db import get_database_connection


class TrainingRepositoryError(Exception):
    """Base class for training repository errors."""


class TrainingRepositoryUnavailable(TrainingRepositoryError):
    """Raised when the database is not configured."""


class TrainingTopicNotFoundError(TrainingRepositoryError):
    """Raised when a training topic cannot be found."""


class TrainingRepository:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        if not self.database_url:
            raise TrainingRepositoryUnavailable("DATABASE_URL is not configured")
        return get_database_connection()

    def list_topics(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        t.id,
                        t.slug,
                        t.title,
                        t.description,
                        count(m.id) as material_count
                    from c3a_app_training_topics t
                    left join c3a_app_training_materials m on m.topic_id = t.id
                    group by t.id
                    order by t.sort_order, t.title
                    """
                )
                rows = cursor.fetchall()

        return [
            {
                "id": str(row["id"]),
                "slug": row["slug"],
                "title": row["title"],
                "description": row["description"],
                "materialCount": row["material_count"],
            }
            for row in rows
        ]

    def list_materials(self, topic_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select id, slug, title, description
                    from c3a_app_training_topics
                    where id = %s
                    """,
                    (topic_id,),
                )
                topic = cursor.fetchone()
                if not topic:
                    raise TrainingTopicNotFoundError(f"Training topic {topic_id} was not found")

                cursor.execute(
                    """
                    select id, topic_id, title, type, summary, body, url,
                           source_name, source_url, duration_minutes
                    from c3a_app_training_materials
                    where topic_id = %s
                    order by sort_order, title
                    """,
                    (topic_id,),
                )
                materials = cursor.fetchall()

        return {
            "topic": {
                "id": str(topic["id"]),
                "slug": topic["slug"],
                "title": topic["title"],
                "description": topic["description"],
                "materialCount": len(materials),
            },
            "materials": [
                {
                    "id": str(material["id"]),
                    "topicId": str(material["topic_id"]),
                    "title": material["title"],
                    "type": material["type"],
                    "summary": material["summary"],
                    "body": material["body"],
                    "url": material["url"],
                    "sourceName": material["source_name"],
                    "sourceUrl": material["source_url"],
                    "durationMinutes": material["duration_minutes"],
                }
                for material in materials
            ],
        }

    def search_materials(self, query: str) -> list[dict[str, Any]]:
        term = query.strip()
        if not term:
            return []

        like = f"%{term}%"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        m.id, m.topic_id, m.title, m.type, m.summary, m.body, m.url,
                        m.source_name, m.source_url, m.duration_minutes,
                        t.title as topic_title, t.slug as topic_slug
                    from c3a_app_training_materials m
                    join c3a_app_training_topics t on t.id = m.topic_id
                    where m.title ilike %(like)s
                        or m.summary ilike %(like)s
                        or m.body ilike %(like)s
                        or m.source_name ilike %(like)s
                        or t.title ilike %(like)s
                    order by t.sort_order, m.sort_order
                    """,
                    {"like": like},
                )
                results = cursor.fetchall()

        return [
            {
                "id": str(row["id"]),
                "topicId": str(row["topic_id"]),
                "title": row["title"],
                "type": row["type"],
                "summary": row["summary"],
                "body": row["body"],
                "url": row["url"],
                "sourceName": row["source_name"],
                "sourceUrl": row["source_url"],
                "durationMinutes": row["duration_minutes"],
                "topicTitle": row["topic_title"],
                "topicSlug": row["topic_slug"],
            }
            for row in results
        ]
