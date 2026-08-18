import { App } from '@microsoft/teams.apps';

type AskResponse = {
  answer?: string;
  citations?: unknown[];
  grounded?: boolean;
  grounded_technology_ids?: Array<string | number>;
};

const app = new App();

const apiBase = process.env.TECHSCOPE_API_BASE_URL || 'http://127.0.0.1:8000';

function textValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

app.on('message', async ({ send, activity }) => {
  const question = textValue(activity.text).trim();

  if (!question) {
    await send('질문을 입력해 주세요.');
    return;
  }

  await send({ type: 'typing' });

  const sessionId =
    textValue(activity.conversation?.id).trim() ||
    `teams-${Date.now()}`;

  const userId =
    textValue(activity.from?.id).trim() ||
    'teams-user';

  try {
    const response = await fetch(`${apiBase}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-TechScope-Session-Id': sessionId,
        'X-TechScope-User-Id': userId,
        'X-TechScope-Channel': 'teams',
      },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`TechScope /ask HTTP ${response.status}: ${body.slice(0, 300)}`);
    }

    const result = (await response.json()) as AskResponse;
    const citations = Array.isArray(result.citations) ? result.citations : [];
    const technologyIds = Array.isArray(result.grounded_technology_ids)
      ? result.grounded_technology_ids
      : [];

    const persisted =
      response.headers.get('x-techscope-cosmos-persisted') || 'unknown';

    const interactionId =
      response.headers.get('x-techscope-interaction-id') || '';

    // Teams is a user-facing surface; keep the response readable.
    await send(result.answer || '답변이 비어 있습니다.');

    const ids = technologyIds.length
      ? technologyIds.slice(0, 12).join(', ')
      : 'None';

    await send(
      [
        `Grounded: ${result.grounded === true ? 'True' : 'False'}`,
        `Citations: ${citations.length}`,
        `Technology IDs: ${ids}`,
        `Cosmos Persisted: ${persisted}`,
        interactionId ? `Interaction ID: ${interactionId}` : '',
      ]
        .filter(Boolean)
        .join('\n')
    );

    // Keep the existing Snapshot Import architecture.
    // A Teams request should update the Power BI snapshot just like the browser UI.
    try {
      await fetch(`${apiBase}/demo/powerbi-sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
    } catch (syncError) {
      console.error('POWERBI_SYNC_NONBLOCKING_ERROR', syncError);
    }
  } catch (error) {
    console.error('TECHSCOPE_TEAMS_HANDLER_ERROR', error);
    await send(
      'TechScope 요청 처리 중 오류가 발생했습니다. 로컬 FastAPI 및 Dev Tunnel 상태를 확인해 주세요.'
    );
  }
});

app
  .start(Number(process.env.PORT || 3978))
  .then(() => {
    console.log('TECHSCOPE_TEAMS_AGENT_READY port=3978');
  })
  .catch((error) => {
    console.error('TECHSCOPE_TEAMS_AGENT_START_FAIL', error);
    process.exitCode = 1;
  });
