/* eslint-env jest */

/** Monta um corpo SSE falso com os frames dados, no formato do /chat/stream. */
function sseBody(frames: unknown[]) {
  const encoder = new TextEncoder();
  const chunks = frames.map((f) => encoder.encode(`data: ${JSON.stringify(f)}\n\n`));
  let i = 0;
  return {
    getReader: () => ({
      read: jest.fn().mockImplementation(() =>
        Promise.resolve(
          i < chunks.length ? { done: false, value: chunks[i++] } : { done: true, value: undefined },
        ),
      ),
    }),
  };
}

describe("chat service token usage", () => {
  beforeEach(() => {
    jest.resetModules();
  });

  test("o evento 'done' entrega a contagem de tokens do turno", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: sseBody([
        { type: "token", text: "oi" },
        {
          type: "done",
          final: "oi",
          usage: { input_tokens: 800, output_tokens: 434, total_tokens: 1234 },
        },
      ]),
    }) as unknown as typeof fetch;
    const { streamChat } = require("../chat") as typeof import("../chat");

    const events: import("../chat").ChatEvent[] = [];
    await streamChat("oi", [], (e) => events.push(e));

    const done = events.find((e) => e.type === "done");
    expect(done).toBeDefined();
    if (done?.type !== "done") throw new Error("esperava evento done");
    expect(done.usage).toEqual({ input_tokens: 800, output_tokens: 434, total_tokens: 1234 });
  });

  test("um provider que não conta tokens não quebra o turno", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: sseBody([{ type: "done", final: "oi" }]),
    }) as unknown as typeof fetch;
    const { streamChat } = require("../chat") as typeof import("../chat");

    const events: import("../chat").ChatEvent[] = [];
    await streamChat("oi", [], (e) => events.push(e));

    const done = events.find((e) => e.type === "done");
    if (done?.type !== "done") throw new Error("esperava evento done");
    expect(done.usage).toBeUndefined();
  });
});

describe("chat service provider-state contract", () => {
  // As variáveis EXPO_PUBLIC_* vêm do jest.globalSetup.js: o babel-preset-expo
  // inlina-as no transform, então defini-las aqui não teria efeito nenhum.
  beforeEach(() => {
    jest.resetModules();
  });

  test("sends the session token and stable conversation id", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: jest.fn().mockResolvedValue({ done: true, value: undefined }),
        }),
      },
    });
    global.fetch = fetchMock as typeof fetch;
    // require (e não `await import`): o jest aqui roda em CJS, e o import
    // dinâmico sobrevive ao babel, quebrando com "A dynamic import callback was
    // invoked without --experimental-vm-modules".
    const { streamChat } = require("../chat") as typeof import("../chat");

    await streamChat("Olá", [], jest.fn(), {
      conversationId: "conversation-123",
    });

    const [, request] = fetchMock.mock.calls[0];
    expect(request.headers["X-QA-Accessibility-Token"]).toBe("session-token");
    expect(JSON.parse(request.body)).toMatchObject({
      message: "Olá",
      conversation_id: "conversation-123",
    });
  });
});
