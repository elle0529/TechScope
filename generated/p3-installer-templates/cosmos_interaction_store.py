from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/p3-cosmos.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CosmosInteractionStore:
    def __init__(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.config = config
        self.partition_path = str(config["partition_path"])
        self.partition_field = self.partition_path.lstrip("/").split("/")[0]

        endpoint = os.getenv("TECHSCOPE_COSMOS_ENDPOINT") or config["endpoint"]
        self.client, self.credential_mode = self._build_client(endpoint, config)
        self.database = self.client.get_database_client(config["database"])
        self.container = self.database.get_container_client(config["container"])

    def _build_client(self, endpoint: str, config: dict[str, Any]):
        credential = DefaultAzureCredential(
            exclude_interactive_browser_credential=True
        )
        client = CosmosClient(endpoint, credential=credential)

        try:
            list(client.list_databases(max_item_count=1))
            return client, "DefaultAzureCredential"
        except Exception:
            cp = subprocess.run(
                [
                    "az", "cosmosdb", "keys", "list",
                    "--name", config["account_name"],
                    "--resource-group", config["resource_group"],
                    "--type", "keys",
                    "--query", "primaryMasterKey",
                    "-o", "tsv",
                    "--only-show-errors",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            key = (cp.stdout or "").strip()
            if cp.returncode != 0 or not key:
                raise RuntimeError(
                    "COSMOS_AUTH_FAILED: DefaultAzureCredential unavailable "
                    "and runtime account-key lookup failed"
                )
            return CosmosClient(endpoint, credential=key), "RuntimeAccountKey"

    def _partition_value(self, session_id: str, doc_id: str) -> str:
        if self.partition_field == "id":
            return doc_id
        if self.partition_field in {"sessionId", "session_id"}:
            return session_id
        return "techscope"

    def _base(self, *, doc_type: str, session_id: str, doc_id: str) -> dict[str, Any]:
        obj = {
            "id": doc_id,
            "type": doc_type,
            "sessionId": session_id,
            "createdAtUtc": _utc_now(),
            "schemaVersion": 1,
        }
        obj[self.partition_field] = self._partition_value(session_id, doc_id)
        return obj

    def create_session(self, *, title: str | None = None) -> dict[str, Any]:
        session_id = str(uuid4())
        doc_id = f"session:{session_id}"
        doc = self._base(doc_type="session", session_id=session_id, doc_id=doc_id)
        doc["title"] = title or "TechScope session"
        self.container.create_item(doc)
        return doc

    def add_interaction(
        self,
        *,
        session_id: str,
        request_id: str,
        question: str,
        answer: str,
        grounded: bool,
        citations: list[Any] | None = None,
        technology_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        doc_id = f"interaction:{request_id}"
        doc = self._base(
            doc_type="interaction",
            session_id=session_id,
            doc_id=doc_id,
        )
        doc.update(
            {
                "requestId": request_id,
                "question": question,
                "answer": answer,
                "grounded": bool(grounded),
                "citations": citations or [],
                "technologyIds": technology_ids or [],
            }
        )
        self.container.upsert_item(doc)
        return doc

    def add_feedback(
        self,
        *,
        session_id: str,
        request_id: str,
        rating: int,
        comment: str | None = None,
    ) -> dict[str, Any]:
        doc_id = f"feedback:{uuid4()}"
        doc = self._base(doc_type="feedback", session_id=session_id, doc_id=doc_id)
        doc.update(
            {
                "requestId": request_id,
                "rating": int(rating),
                "comment": comment,
            }
        )
        self.container.create_item(doc)
        return doc

    def get_session_documents(self, session_id: str) -> list[dict[str, Any]]:
        query = "SELECT * FROM c WHERE c.sessionId = @sessionId"
        return list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@sessionId", "value": session_id}],
                enable_cross_partition_query=True,
            )
        )
