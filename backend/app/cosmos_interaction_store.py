from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/cosmos-runtime.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    import json

    return json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )


class CosmosInteractionStore:
    def __init__(self) -> None:
        cfg = load_config()

        self.endpoint = str(cfg["endpoint"])
        self.database_name = str(cfg["database"])
        containers = cfg["containers"]

        self.sessions_name = str(containers["sessions"])
        self.messages_name = str(containers["messages"])
        self.feedback_name = str(containers["feedback"])

        self.credential = DefaultAzureCredential()
        self.client = CosmosClient(
            url=self.endpoint,
            credential=self.credential,
        )
        self.database = self.client.get_database_client(
            self.database_name
        )
        self.sessions = self.database.get_container_client(
            self.sessions_name
        )
        self.messages = self.database.get_container_client(
            self.messages_name
        )
        self.feedback = self.database.get_container_client(
            self.feedback_name
        )

    def runtime_probe(self) -> dict[str, Any]:
        props = self.sessions.read()

        return {
            "data_plane": bool(props.get("id") == self.sessions_name),
            "database": self.database_name,
            "containers": {
                "sessions": self.sessions_name,
                "messages": self.messages_name,
                "feedback": self.feedback_name,
            },
        }

    def ensure_session(
        self,
        session_id: str,
        *,
        user_id: str,
        channel: str,
    ) -> dict[str, Any]:
        now = utc_now()

        try:
            item = self.sessions.read_item(
                item=session_id,
                partition_key=session_id,
            )
            item["updated_at"] = now
            item["user_id"] = user_id or item.get(
                "user_id",
                "anonymous",
            )
            item["channel"] = channel or item.get(
                "channel",
                "unknown",
            )

            return self.sessions.upsert_item(item)
        except CosmosResourceNotFoundError:
            item = {
                "id": session_id,
                "session_id": session_id,
                "user_id": user_id or "anonymous",
                "channel": channel or "unknown",
                "created_at": now,
                "updated_at": now,
                "kind": "session",
            }
            return self.sessions.create_item(item)

    def create_session(
        self,
        *,
        user_id: str,
        channel: str,
        requested_session_id: str | None = None,
    ) -> dict[str, Any]:
        session_id = (
            requested_session_id.strip()
            if requested_session_id
            else str(uuid.uuid4())
        )

        return self.ensure_session(
            session_id,
            user_id=user_id,
            channel=channel,
        )

    def append_message(
        self,
        *,
        session_id: str,
        interaction_id: str,
        role: str,
        content: str,
        grounded: bool | None = None,
        citations: list[Any] | None = None,
        grounded_technology_ids: list[Any] | None = None,
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "interaction_id": interaction_id,
            "role": role,
            "content": content,
            "grounded": grounded,
            "citations": citations or [],
            "grounded_technology_ids": grounded_technology_ids or [],
            "created_at": utc_now(),
            "kind": "message",
        }

        return self.messages.create_item(item)

    def add_feedback(
        self,
        *,
        session_id: str,
        interaction_id: str,
        score: int,
        comment: str,
        user_id: str,
    ) -> dict[str, Any]:
        item = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "interaction_id": interaction_id,
            "score": int(score),
            "comment": comment or "",
            "user_id": user_id or "anonymous",
            "created_at": utc_now(),
            "kind": "feedback",
        }

        return self.feedback.create_item(item)

    def get_session_bundle(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        session = self.sessions.read_item(
            item=session_id,
            partition_key=session_id,
        )

        params = [
            {
                "name": "@session_id",
                "value": session_id,
            }
        ]

        messages = list(
            self.messages.query_items(
                query=(
                    "SELECT * FROM c "
                    "WHERE c.session_id = @session_id "
                    "ORDER BY c.created_at ASC"
                ),
                parameters=params,
                partition_key=session_id,
            )
        )

        feedback = list(
            self.feedback.query_items(
                query=(
                    "SELECT * FROM c "
                    "WHERE c.session_id = @session_id "
                    "ORDER BY c.created_at ASC"
                ),
                parameters=params,
                partition_key=session_id,
            )
        )

        return {
            "session": session,
            "messages": messages,
            "feedback": feedback,
        }
