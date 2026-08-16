from __future__ import annotations

import os
import uuid

from mssql_python import connect

from .core import AskResult


class AzureSqlInteractionSink:
    """Persist successful RAG operations to the TechScope Azure SQL serving mart.

    Grounded technology relationships are derived only from
    AskResult.grounded_technology_ids, which in the current RAG service are
    assembled from the actual grounding SearchHit metadata.
    """

    def __init__(
        self,
        *,
        server: str,
        database: str,
        model_name: str,
    ) -> None:
        self.server = server
        self.database = database
        self.model_name = model_name

    @classmethod
    def from_env(cls, *, model_name: str) -> "AzureSqlInteractionSink":
        return cls(
            server=os.getenv(
                "TECHSCOPE_SQL_SERVER",
                "sql-techscope-dev-239bd206.database.windows.net",
            ),
            database=os.getenv(
                "TECHSCOPE_SQL_DATABASE",
                "sqldb-techscope-dev",
            ),
            model_name=model_name,
        )

    def _connection_string(self) -> str:
        return (
            f"Server={self.server};"
            f"Database={self.database};"
            "Authentication=ActiveDirectoryDefault;"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
        )

    def record(
        self,
        *,
        question: str,
        result: AskResult,
        latency_ms: int,
    ) -> None:
        del question  # The operational mart intentionally does not persist question text.

        request_id = str(uuid.uuid4())
        grounding_ids = tuple(
            sorted({technology_id for technology_id in result.grounded_technology_ids if technology_id})
        )

        conn = connect(self._connection_string())
        try:
            cursor = conn.cursor()

            resolved: dict[str, int] = {}
            for technology_id in grounding_ids:
                cursor.execute(
                    """
                    SELECT TechnologyKey
                    FROM techscope.DimTechnology
                    WHERE TechnologyId = ?
                    """,
                    (technology_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError(
                        f"Grounding technology ID not found in DimTechnology: {technology_id}"
                    )
                resolved[technology_id] = int(row[0])

            cursor.execute(
                """
                INSERT INTO techscope.FactAIRequest(
                    RequestId,
                    RequestTimestamp,
                    Status,
                    LatencyMs,
                    RetrievedChunkCount,
                    CitationFlag,
                    FeedbackScore,
                    ErrorType,
                    ModelName
                )
                OUTPUT INSERTED.RequestKey
                VALUES(
                    CONVERT(uniqueidentifier, ?),
                    SYSUTCDATETIME(),
                    'success',
                    ?,
                    ?,
                    ?,
                    NULL,
                    NULL,
                    ?
                )
                """,
                (
                    request_id,
                    int(latency_ms),
                    len(set(result.retrieved_chunk_ids)),
                    1 if result.citations else 0,
                    self.model_name,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("FactAIRequest insert did not return RequestKey")
            request_key = int(inserted[0])

            for technology_id in grounding_ids:
                cursor.execute(
                    """
                    INSERT INTO techscope.BridgeAIRequestTechnology(
                        RequestKey,
                        TechnologyKey
                    )
                    VALUES(?, ?)
                    """,
                    (request_key, resolved[technology_id]),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
