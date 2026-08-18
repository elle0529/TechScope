from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

from fastapi import Body, FastAPI, HTTPException

from .cosmos_interaction_store import CosmosInteractionStore


COSMOS_RUNTIME_VERSION = "p3a2-v1"


def _header(
    scope: dict[str, Any],
    name: str,
) -> str | None:
    target = name.lower().encode("latin-1")

    for key, value in scope.get("headers") or []:
        if key.lower() == target:
            return value.decode(
                "utf-8",
                errors="ignore",
            )

    return None


class CosmosAskPersistenceMiddleware:
    def __init__(
        self,
        app,
        *,
        store: CosmosInteractionStore,
    ) -> None:
        self.app = app
        self.store = store

    async def __call__(
        self,
        scope,
        receive,
        send,
    ):
        if (
            scope.get("type") != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/ask"
        ):
            await self.app(
                scope,
                receive,
                send,
            )
            return

        chunks: list[bytes] = []
        more_body = True

        while more_body:
            message = await receive()

            if message.get("type") != "http.request":
                continue

            chunks.append(
                message.get("body", b"")
            )
            more_body = bool(
                message.get(
                    "more_body",
                    False,
                )
            )

        request_body = b"".join(chunks)
        replayed = False

        async def replay_receive():
            nonlocal replayed

            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": request_body,
                    "more_body": False,
                }

            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }

        response_messages: list[dict[str, Any]] = []

        async def capture_send(message):
            response_messages.append(message)

        await self.app(
            scope,
            replay_receive,
            capture_send,
        )

        status_code = 500

        for message in response_messages:
            if message.get("type") == "http.response.start":
                status_code = int(
                    message.get(
                        "status",
                        500,
                    )
                )
                break

        session_id = (
            _header(
                scope,
                "x-techscope-session-id",
            )
            or str(uuid.uuid4())
        )
        user_id = (
            _header(
                scope,
                "x-techscope-user-id",
            )
            or "anonymous"
        )
        channel = (
            _header(
                scope,
                "x-techscope-channel",
            )
            or "web"
        )
        interaction_id = str(uuid.uuid4())

        cosmos_persisted = False

        try:
            request_obj = json.loads(
                request_body.decode("utf-8")
            )
        except Exception:
            request_obj = {}

        question = str(
            request_obj.get("question")
            or request_obj.get("query")
            or ""
        ).strip()

        response_body = b"".join(
            message.get("body", b"")
            for message in response_messages
            if message.get("type")
            == "http.response.body"
        )

        try:
            response_obj = json.loads(
                response_body.decode("utf-8")
            )
        except Exception:
            response_obj = {}

        if (
            200 <= status_code < 300
            and question
            and isinstance(
                response_obj,
                dict,
            )
        ):
            try:
                await asyncio.to_thread(
                    self.store.ensure_session,
                    session_id,
                    user_id=user_id,
                    channel=channel,
                )

                await asyncio.to_thread(
                    self.store.append_message,
                    session_id=session_id,
                    interaction_id=interaction_id,
                    role="user",
                    content=question,
                )

                await asyncio.to_thread(
                    self.store.append_message,
                    session_id=session_id,
                    interaction_id=interaction_id,
                    role="assistant",
                    content=str(
                        response_obj.get(
                            "answer",
                            "",
                        )
                    ),
                    grounded=response_obj.get(
                        "grounded"
                    ),
                    citations=list(
                        response_obj.get(
                            "citations"
                        )
                        or []
                    ),
                    grounded_technology_ids=list(
                        response_obj.get(
                            "grounded_technology_ids"
                        )
                        or []
                    ),
                )

                cosmos_persisted = True
            except Exception as exc:
                print(
                    "COSMOS_ASK_PERSISTENCE_ERROR="
                    + type(exc).__name__,
                    flush=True,
                )

        for message in response_messages:
            if message.get("type") == "http.response.start":
                headers = list(
                    message.get(
                        "headers"
                    )
                    or []
                )

                headers.extend(
                    [
                        (
                            b"x-techscope-session-id",
                            session_id.encode(
                                "utf-8"
                            ),
                        ),
                        (
                            b"x-techscope-interaction-id",
                            interaction_id.encode(
                                "utf-8"
                            ),
                        ),
                        (
                            b"x-techscope-cosmos-persisted",
                            (
                                b"true"
                                if cosmos_persisted
                                else b"false"
                            ),
                        ),
                    ]
                )

                message["headers"] = headers
                break

        for message in response_messages:
            await send(message)


def install_cosmos_runtime(
    app: FastAPI,
) -> None:
    if getattr(
        app.state,
        "techscope_cosmos_runtime_installed",
        False,
    ):
        return

    store = CosmosInteractionStore()

    app.state.techscope_cosmos_store = store
    app.add_middleware(
        CosmosAskPersistenceMiddleware,
        store=store,
    )

    @app.get(
        "/demo/cosmos-runtime"
    )
    async def cosmos_runtime():
        try:
            probe = await asyncio.to_thread(
                store.runtime_probe
            )

            return {
                "version":
                    COSMOS_RUNTIME_VERSION,
                "pid": os.getpid(),
                "configured": True,
                "data_plane": bool(
                    probe.get(
                        "data_plane"
                    )
                ),
                "database": probe.get(
                    "database"
                ),
                "containers": probe.get(
                    "containers"
                ),
                "auth":
                    "DefaultAzureCredential",
                "account_key_persisted":
                    False,
            }
        except Exception as exc:
            return {
                "version":
                    COSMOS_RUNTIME_VERSION,
                "pid": os.getpid(),
                "configured": True,
                "data_plane": False,
                "error_type":
                    type(exc).__name__,
            }

    @app.post(
        "/cosmos/session"
    )
    async def create_session(
        body: dict[str, Any] = Body(
            default_factory=dict
        ),
    ):
        try:
            item = await asyncio.to_thread(
                store.create_session,
                user_id=str(
                    body.get(
                        "user_id",
                        "anonymous",
                    )
                ),
                channel=str(
                    body.get(
                        "channel",
                        "web",
                    )
                ),
                requested_session_id=(
                    str(
                        body.get(
                            "session_id"
                        )
                    )
                    if body.get(
                        "session_id"
                    )
                    else None
                ),
            )

            return {
                "session_id":
                    item["session_id"],
                "user_id":
                    item["user_id"],
                "channel":
                    item["channel"],
            }
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Cosmos session persistence failed: "
                    + type(exc).__name__
                ),
            ) from exc

    @app.get(
        "/cosmos/session/{session_id}"
    )
    async def get_session(
        session_id: str,
    ):
        try:
            return await asyncio.to_thread(
                store.get_session_bundle,
                session_id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Session not found or unavailable: "
                    + type(exc).__name__
                ),
            ) from exc

    @app.post(
        "/cosmos/feedback"
    )
    async def add_feedback(
        body: dict[str, Any] = Body(...)
    ):
        session_id = str(
            body.get(
                "session_id"
            )
            or ""
        ).strip()
        interaction_id = str(
            body.get(
                "interaction_id"
            )
            or ""
        ).strip()

        if not session_id:
            raise HTTPException(
                status_code=400,
                detail="session_id is required",
            )

        if not interaction_id:
            raise HTTPException(
                status_code=400,
                detail="interaction_id is required",
            )

        score = int(
            body.get(
                "score",
                0,
            )
        )

        if score not in (-1, 0, 1):
            raise HTTPException(
                status_code=400,
                detail="score must be -1, 0, or 1",
            )

        try:
            item = await asyncio.to_thread(
                store.add_feedback,
                session_id=session_id,
                interaction_id=interaction_id,
                score=score,
                comment=str(
                    body.get(
                        "comment",
                        "",
                    )
                ),
                user_id=str(
                    body.get(
                        "user_id",
                        "anonymous",
                    )
                ),
            )

            return {
                "feedback_id": item["id"],
                "session_id": session_id,
                "interaction_id":
                    interaction_id,
                "score": score,
            }
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Cosmos feedback persistence failed: "
                    + type(exc).__name__
                ),
            ) from exc

    app.state.techscope_cosmos_runtime_installed = True
