import { App } from "@microsoft/teams.apps";
import { askTechScope, formatTechScopeAnswer } from "./techscope-client.js";
const app = new App();
app.on("message", async ({ activity, send }) => {
    const text = activity.text?.trim();
    if (!text) {
        await send("질문을 입력해 주세요.");
        return;
    }
    try {
        const result = await askTechScope(text);
        await send(formatTechScopeAnswer(result));
    }
    catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        await send(`TechScope API error: ${message}`);
    }
});
app.start().catch((error) => {
    console.error("TEAMS_APP_START_FAIL", error);
    process.exitCode = 1;
});
