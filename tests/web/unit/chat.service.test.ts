import { TextDecoder, TextEncoder } from "util";

// jsdom não expõe TextDecoder/TextEncoder por padrão; chat.ts usa TextDecoder.
(global as unknown as { TextDecoder: typeof TextDecoder }).TextDecoder = TextDecoder;
(global as unknown as { TextEncoder: typeof TextEncoder }).TextEncoder = TextEncoder;

import { streamChat, getModels, type ChatEvent } from "../../src/services/chat";

function sseResponse(chunks: string[]) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => {
          if (i < chunks.length) return { done: false, value: enc.encode(chunks[i++]) };
          return { done: true, value: undefined };
        },
      }),
    },
  };
}

describe("chat service (SSE)", () => {
  afterEach(() => jest.restoreAllMocks());

  it("streamChat parseia múltiplos eventos SSE", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      sseResponse([
        'data: {"type":"token","text":"Ola"}\n\n',
        'data: {"type":"done","final":"Ola"}\n\n',
      ]),
    ) as unknown as typeof fetch;

    const events: ChatEvent[] = [];
    await streamChat("oi", [], (e) => events.push(e));

    expect(events).toEqual([
      { type: "token", text: "Ola" },
      { type: "done", final: "Ola" },
    ]);
  });

  it("streamChat remonta um chunk SSE partido entre reads", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      sseResponse(['data: {"type":"to', 'ken","text":"Hi"}\n\n']),
    ) as unknown as typeof fetch;

    const events: ChatEvent[] = [];
    await streamChat("oi", [], (e) => events.push(e));

    expect(events).toEqual([{ type: "token", text: "Hi" }]);
  });

  it("streamChat envia provider/model no body", async () => {
    const fetchMock = jest.fn().mockResolvedValue(sseResponse([])) as unknown as typeof fetch;
    global.fetch = fetchMock;

    await streamChat("oi", [], () => {}, { provider: "anthropic", model: "claude-opus-4-5" });

    const body = JSON.parse((fetchMock as unknown as jest.Mock).mock.calls[0][1].body);
    expect(body.provider).toBe("anthropic");
    expect(body.model).toBe("claude-opus-4-5");
  });

  it("streamChat lança em erro HTTP", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500, body: null }) as unknown as typeof fetch;
    await expect(streamChat("oi", [], () => {})).rejects.toThrow(/500/);
  });

  it("getModels retorna os providers do backend", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ providers: [{ id: "openai", label: "OpenAI", models: ["gpt-5.2"] }] }),
    }) as unknown as typeof fetch;

    const providers = await getModels();
    expect(providers).toHaveLength(1);
    expect(providers[0].id).toBe("openai");
    expect(providers[0].models).toContain("gpt-5.2");
  });

  it("getModels lança em erro HTTP", async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 404 }) as unknown as typeof fetch;
    await expect(getModels()).rejects.toThrow();
  });
});
