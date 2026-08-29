/**
 * @jest-environment jsdom
 */
/* eslint-env jest, node, browser */

import React, { useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

import { useDialogFocus } from "../useDialogFocus";

/**
 * Teste comportamental: monta um diálogo a sério no DOM do jsdom e exercita o
 * teclado. Nada aqui procura strings no código-fonte — o que se verifica é o
 * `document.activeElement` depois de Tab, Shift+Tab, Escape e desmontagem, que
 * é exatamente o que quem navega por teclado ou leitor de tela sente.
 */

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
global.IS_REACT_ACT_ENVIRONMENT = true;

interface DialogProps {
  active: boolean;
  onDismiss: () => void;
  focusFirstControl?: boolean;
}

function Dialog({ active, onDismiss, focusFirstControl }: DialogProps) {
  const containerRef = useRef<HTMLElement | null>(null);
  useDialogFocus({
    active,
    containerRef,
    onDismiss,
    getInitialFocus: focusFirstControl
      ? (container) => container.querySelector<HTMLElement>("button")
      : undefined,
  });
  if (!active) return null;
  return (
    <div ref={containerRef as React.RefObject<HTMLDivElement>} role="dialog" aria-modal="true">
      <button type="button" id="first">
        Primeiro
      </button>
      <button type="button" id="last">
        Último
      </button>
    </div>
  );
}

let host: HTMLDivElement;
let root: Root;
let outside: HTMLButtonElement;

beforeEach(() => {
  outside = document.createElement("button");
  outside.id = "outside";
  document.body.appendChild(outside);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.replaceChildren();
});

/** O foco inicial é agendado num `requestAnimationFrame`. */
async function flushFrame(): Promise<void> {
  await act(async () => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  });
}

function mount(props: DialogProps): void {
  act(() => root.render(<Dialog {...props} />));
}

function press(key: string, init: { shiftKey?: boolean } = {}): void {
  act(() => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...init }));
  });
}

describe("useDialogFocus — foco inicial", () => {
  test("por padrão o foco vai para o contêiner, não para um botão", async () => {
    mount({ active: true, onDismiss: () => {} });
    await flushFrame();
    const container = host.querySelector('[role="dialog"]');
    expect(document.activeElement).toBe(container);
    // Um pedido de aprovação nunca deixa um botão destrutivo armado.
    expect(document.activeElement?.id).not.toBe("first");
  });

  test("o contêiner fica focável para poder receber foco programático", async () => {
    mount({ active: true, onDismiss: () => {} });
    await flushFrame();
    expect(host.querySelector('[role="dialog"]')?.getAttribute("tabindex")).toBe("-1");
  });

  test("quem pede foco no primeiro controle recebe o primeiro controle", async () => {
    mount({ active: true, onDismiss: () => {}, focusFirstControl: true });
    await flushFrame();
    expect(document.activeElement?.id).toBe("first");
  });
});

describe("useDialogFocus — Tab preso no diálogo", () => {
  test("Tab no último controle volta ao primeiro", async () => {
    mount({ active: true, onDismiss: () => {} });
    await flushFrame();
    host.querySelector<HTMLElement>("#last")?.focus();
    press("Tab");
    expect(document.activeElement?.id).toBe("first");
  });

  test("Shift+Tab no primeiro controle salta para o último", async () => {
    mount({ active: true, onDismiss: () => {} });
    await flushFrame();
    host.querySelector<HTMLElement>("#first")?.focus();
    press("Tab", { shiftKey: true });
    expect(document.activeElement?.id).toBe("last");
  });

  test("o foco nunca escapa para fora do diálogo", async () => {
    mount({ active: true, onDismiss: () => {} });
    await flushFrame();
    host.querySelector<HTMLElement>("#last")?.focus();
    press("Tab");
    press("Tab");
    expect(host.contains(document.activeElement)).toBe(true);
  });
});

describe("useDialogFocus — saída", () => {
  test("Escape pede a saída", async () => {
    const onDismiss = jest.fn();
    mount({ active: true, onDismiss });
    await flushFrame();
    press("Escape");
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  test("ao fechar, o foco volta a quem estava trabalhando antes", async () => {
    outside.focus();
    expect(document.activeElement).toBe(outside);
    mount({ active: true, onDismiss: () => {} });
    await flushFrame();
    expect(document.activeElement).not.toBe(outside);
    mount({ active: false, onDismiss: () => {} });
    expect(document.activeElement).toBe(outside);
  });
});

describe("useDialogFocus — inativo", () => {
  test("com `active` a falso não rouba o foco nem escuta o teclado", async () => {
    outside.focus();
    const onDismiss = jest.fn();
    mount({ active: false, onDismiss });
    await flushFrame();
    press("Escape");
    expect(onDismiss).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(outside);
  });
});
