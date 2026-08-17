export interface TechScopeCitation {
  title?: string;
  source?: string;
  url?: string;
  [key: string]: unknown;
}

export interface TechScopeAskResponse {
  answer?: string;
  grounded?: boolean;
  citations?: TechScopeCitation[];
  technology_ids?: string[];
  grounded_technology_ids?: string[];
  [key: string]: unknown;
}

export async function askTechScope(
  question: string,
  baseUrl = process.env.TECHSCOPE_API_BASE_URL ?? "http://127.0.0.1:8000",
): Promise<TechScopeAskResponse> {
  const normalized = question.trim();
  if (!normalized) {
    throw new Error("QUESTION_EMPTY");
  }

  const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/ask`, {
    method: "POST",
    headers: {
      "content-type": "application/json"
    },
    body: JSON.stringify({
      question: normalized
    })
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`TECHSCOPE_API_${response.status}: ${body.slice(0, 500)}`);
  }

  return await response.json() as TechScopeAskResponse;
}

export function formatTechScopeAnswer(result: TechScopeAskResponse): string {
  const answer = String(result.answer ?? "No answer returned.");
  const grounded = result.grounded === true ? "Yes" : "No";

  const ids = (
    result.grounded_technology_ids ??
    result.technology_ids ??
    []
  ).map(String);

  const citations = Array.isArray(result.citations)
    ? result.citations
    : [];

  const lines: string[] = [
    answer,
    "",
    `Grounded: ${grounded}`,
  ];

  if (ids.length > 0) {
    lines.push(`Technology IDs: ${ids.join(", ")}`);
  }

  if (citations.length > 0) {
    lines.push(`Citations: ${citations.length}`);
    citations.slice(0, 5).forEach((citation, index) => {
      const label =
        citation.title ??
        citation.source ??
        citation.url ??
        `Citation ${index + 1}`;
      lines.push(`${index + 1}. ${String(label)}`);
    });
  }

  return lines.join("\n");
}
