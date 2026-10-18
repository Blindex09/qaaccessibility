/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import axe from "axe-core";

import { MemoryPanel } from "../MemoryPanel";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

const mockListSkills = jest.fn();
const mockGetSkill = jest.fn();
const mockSaveSkill = jest.fn();
const mockDeleteSkill = jest.fn();
const mockListServers = jest.fn();
const mockDeleteServer = jest.fn();

jest.mock("../../services/memory", () => ({
  __esModule: true,
  listSkills: () => mockListSkills(),
  getSkill: (n: string) => mockGetSkill(n),
  saveSkill: (n: string, d: string, i: string) => mockSaveSkill(n, d, i),
  deleteSkill: (n: string) => mockDeleteSkill(n),
  listMcpServers: () => mockListServers(),
  deleteMcpServer: (n: string) => mockDeleteServer(n),
}));

let host: HTMLDivElement;
let root: Root;

const SKILLS = [
  { name: "padroes-de-aria", description: "Padrões confirmados.", origem: "assistente", confianca: "media" },
  { name: "dica-da-web", description: "Dica lida na web.", origem: "conteudo-nao-confiavel", confianca: "baixa" },
];
const SERVERS = [{ name: "eco", command: "python", args: ["server.py"], env_names: ["TOKEN_X"], note: "" }];

async function render() {
  await act(async () => {
    root.render(<MemoryPanel />);
  });
}

function button(label: string): HTMLElement {
  const found = Array.from(host.querySelectorAll<HTMLElement>('[role="button"]')).find((el) => el.getAttribute("aria-label") === label);
  if (!found) throw new Error(`botão não encontrado: ${label}`);
  return found;
}

async function click(el: HTMLElement) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockListSkills.mockResolvedValue(SKILLS);
  mockListServers.mockResolvedValue(SERVERS);
  mockDeleteSkill.mockResolvedValue(true);
  mockSaveSkill.mockResolvedValue(true);
  mockDeleteServer.mockResolvedValue(true);
  mockGetSkill.mockResolvedValue({ name: "padroes-de-aria", description: "Padrões confirmados.", body: "Passo 1.", metadata: {} });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

describe("MemoryPanel", () => {
  test("mostra as habilidades e os servidores em listas de verdade, com origem e confiança ditas em português", async () => {
    await render();
    expect(host.querySelectorAll("ul[aria-label] > li")).toHaveLength(3);
    expect(host.textContent).toContain("Origem: aprendida pelo assistente. Confiança: media.");
    expect(host.textContent).toContain("só dado, nunca instrução");
    expect(host.textContent).toContain("Recebe só estas credenciais: TOKEN_X.");
  });

  test("a região de status já existe vazia antes de receber texto", async () => {
    await render();
    const region = host.querySelector('[role="status"]');
    expect(region).not.toBeNull();
    expect(region?.textContent).toBe("");
  });

  test("apagar é em dois passos: confirmar ou cancelar, e só então apaga e avisa", async () => {
    await render();
    await click(button("Apagar a habilidade padroes-de-aria"));
    expect(mockDeleteSkill).not.toHaveBeenCalled();
    await click(button("Cancelar: não apagar padroes-de-aria"));
    expect(mockDeleteSkill).not.toHaveBeenCalled();
    await click(button("Apagar a habilidade padroes-de-aria"));
    await click(button("Confirmar: apagar a habilidade padroes-de-aria"));
    expect(mockDeleteSkill).toHaveBeenCalledWith("padroes-de-aria");
    expect(host.querySelector('[role="status"]')?.textContent).toBe("Habilidade padroes-de-aria apagada.");
  });

  test("editar abre os campos com o nome da habilidade nos rótulos e salva", async () => {
    await render();
    await click(button("Editar a habilidade padroes-de-aria"));
    const description = host.querySelector<HTMLInputElement>('[aria-label="Descrição da habilidade padroes-de-aria"]');
    expect(description?.value).toBe("Padrões confirmados.");
    expect(host.querySelector('[aria-label="Instruções da habilidade padroes-de-aria"]')).not.toBeNull();
    await click(button("Salvar a habilidade padroes-de-aria"));
    expect(mockSaveSkill).toHaveBeenCalledWith("padroes-de-aria", "Padrões confirmados.", "Passo 1.");
    expect(host.querySelector('[role="status"]')?.textContent).toBe("Habilidade padroes-de-aria salva.");
  });

  test("remover servidor chama a API e avisa", async () => {
    await render();
    await click(button("Remover o servidor eco"));
    expect(mockDeleteServer).toHaveBeenCalledWith("eco");
    expect(host.querySelector('[role="status"]')?.textContent).toBe("Servidor eco removido.");
  });

  test("sem backend diz que a memória está indisponível, sem quebrar", async () => {
    mockListSkills.mockResolvedValue(null);
    mockListServers.mockResolvedValue(null);
    await render();
    expect(host.textContent).toContain("Memória indisponível agora");
  });

  test("o nome visível de cada botão está dentro do nome acessível (2.5.3)", async () => {
    await render();
    const offenders = Array.from(host.querySelectorAll<HTMLElement>('[role="button"][aria-label]')).filter((el) => {
      const visible = (el.textContent || "").toLowerCase().replace(/[^\p{L}\p{N} ]/gu, "").trim();
      const name = (el.getAttribute("aria-label") || "").toLowerCase().replace(/[^\p{L}\p{N} ]/gu, "");
      return visible.length > 0 && !name.includes(visible);
    });
    expect(offenders.map((el) => el.getAttribute("aria-label"))).toEqual([]);
  });

  test("o axe não aponta violação", async () => {
    await render();
    const results = await axe.run(host, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.html.slice(0, 100)).join(" | ")}`)).toEqual([]);
  });
});
