import { createServer } from "node:http";
import { once } from "node:events";
import {
  askTechScope,
  formatTechScopeAnswer,
} from "./techscope-client.js";

async function main(): Promise<void> {
  let observedMethod = "";
  let observedPath = "";
  let observedQuestion = "";

  const server = createServer((request, response) => {
    observedMethod = request.method ?? "";
    observedPath = request.url ?? "";

    const chunks: Buffer[] = [];

    request.on("data", (chunk) => {
      chunks.push(Buffer.from(chunk));
    });

    request.on("end", () => {
      const body = Buffer.concat(chunks).toString("utf8");
      const parsed = JSON.parse(body) as { question?: string };
      observedQuestion = parsed.question ?? "";

      response.writeHead(200, {
        "content-type": "application/json"
      });

      response.end(JSON.stringify({
        answer: "Databricks performs normalization and Gold/RAG processing.",
        grounded: true,
        citations: [
          {
            title: "TechScope architecture"
          }
        ],
        grounded_technology_ids: [
          "T_TEST_001"
        ]
      }));
    });
  });

  server.listen(0, "127.0.0.1");
  await once(server, "listening");

  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("SMOKE_SERVER_ADDRESS_INVALID");
  }

  try {
    const result = await askTechScope(
      "What role does Databricks play in TechScope?",
      `http://127.0.0.1:${address.port}`,
    );

    const formatted = formatTechScopeAnswer(result);

    if (observedMethod !== "POST") {
      throw new Error(`METHOD_MISMATCH=${observedMethod}`);
    }

    if (observedPath !== "/ask") {
      throw new Error(`PATH_MISMATCH=${observedPath}`);
    }

    if (observedQuestion !== "What role does Databricks play in TechScope?") {
      throw new Error(`QUESTION_MISMATCH=${observedQuestion}`);
    }

    if (!formatted.includes("Grounded: Yes")) {
      throw new Error("GROUNDING_FORMAT_MISSING");
    }

    if (!formatted.includes("T_TEST_001")) {
      throw new Error("TECHNOLOGY_ID_FORMAT_MISSING");
    }

    if (!formatted.includes("Citations: 1")) {
      throw new Error("CITATION_FORMAT_MISSING");
    }

    console.log("TEAMS_FASTAPI_ADAPTER_SMOKE=PASS");
    console.log("HTTP_METHOD=POST");
    console.log("HTTP_PATH=/ask");
    console.log("QUESTION_FORWARDING=PASS");
    console.log("ANSWER_FORMATTING=PASS");
    console.log("GROUNDING_FORMATTING=PASS");
    console.log("CITATION_FORMATTING=PASS");
    console.log("TECHNOLOGY_ID_FORMATTING=PASS");
  } finally {
    server.close();
    await once(server, "close");
  }
}

main().catch((error) => {
  console.error("TEAMS_FASTAPI_ADAPTER_SMOKE=FAIL", error);
  process.exit(1);
});
