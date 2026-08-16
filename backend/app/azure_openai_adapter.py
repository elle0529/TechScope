from __future__ import annotations

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

from .core import SearchHit


SYSTEM_INSTRUCTIONS = """You are TechScope technical support.
Answer only from the supplied retrieval context.
Do not invent facts that are not supported by the context.
If the context is insufficient, explicitly say that the available TechScope evidence is insufficient.
Keep technology names and source identifiers faithful to the context.
"""


class AzureOpenAIResponsesGenerator:
    def __init__(
        self,
        *,
        endpoint: str,
        deployment: str,
    ) -> None:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://ai.azure.com/.default",
        )
        self.client = OpenAI(
            base_url=endpoint.rstrip("/") + "/openai/v1/",
            api_key=token_provider,
        )
        self.deployment = deployment

    def generate(self, question: str, hits: list[SearchHit]) -> str:
        context_blocks = []
        for hit in hits:
            context_blocks.append(
                "\n".join(
                    [
                        f"[chunk_id={hit.chunk_id}]",
                        f"[source_id={hit.source_id or ''}]",
                        f"[technology={', '.join(hit.technology)}]",
                        f"[technology_ids={', '.join(hit.technology_ids)}]",
                        f"[category={', '.join(hit.category)}]",
                        f"[architecture_layer={', '.join(hit.architecture_layer)}]",
                        f"[evidence_type={hit.evidence_type or ''}]",
                        hit.content,
                    ]
                )
            )

        prompt = (
            "QUESTION:\n"
            + question
            + "\n\nRETRIEVAL CONTEXT:\n"
            + "\n\n---\n\n".join(context_blocks)
        )

        response = self.client.responses.create(
            model=self.deployment,
            instructions=SYSTEM_INSTRUCTIONS,
            input=prompt,
        )
        return response.output_text
