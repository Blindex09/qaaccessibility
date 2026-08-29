import { useEffect, useRef, type RefObject } from "react";

/**
 * Gestão de foco do padrão WAI-ARIA Dialog, num único sítio.
 *
 * Por que existe: o modal de chave de API (`ChatScreen`), o `LivePreviewModal`
 * e o pedido de aprovação do `ClarifyPanel` precisam exatamente do mesmo
 * comportamento — prender o Tab dentro do diálogo, fechar no Escape e devolver
 * o foco a quem estava trabalhando antes de o diálogo abrir. Estava duplicado
 * em duas telas; um terceiro reimplementá-lo seria a garantia de que as três
 * cópias divergiriam.
 */

/** Elementos que recebem foco por teclado dentro de um diálogo. */
export const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input:not([disabled]), select, textarea';

/** Qualquer coisa focável: nós do DOM e refs de componentes React Native. */
interface Focusable {
  focus?: () => void;
}

export interface DialogFocusOptions {
  /** O diálogo está montado e visível. Se falso, o hook não faz nada. */
  active: boolean;
  /** contêiner do diálogo — delimita o ciclo de Tab. */
  containerRef: RefObject<HTMLElement | null>;
  /** Pedido de saída (Escape). Tipicamente fechar ou negar. */
  onDismiss: () => void;
  /**
   * Alvo do foco inicial. Por padrão é o próprio contêiner: o leitor de tela
   * lê o nome e o conteúdo do diálogo sem deixar nenhum botão armado — o que
   * importa quando o diálogo pede aprovação de uma ação destrutiva.
   */
  getInitialFocus?: (container: HTMLElement) => Focusable | null | undefined;
}

export function useDialogFocus({
  active,
  containerRef,
  onDismiss,
  getInitialFocus,
}: DialogFocusOptions): void {
  // Os callbacks mudam de identidade a cada render; guardá-los em refs impede
  // que o efeito se remonte e volte a roubar o foco a meio da interação.
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;
  const getInitialFocusRef = useRef(getInitialFocus);
  getInitialFocusRef.current = getInitialFocus;

  useEffect(() => {
    if (!active || typeof document === "undefined") return;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    function focusableItems(): HTMLElement[] {
      const container = containerRef.current;
      return container
        ? Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        : [];
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onDismissRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusableItems();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function focusInitial() {
      const container = containerRef.current;
      if (!container) return;
      const resolve = getInitialFocusRef.current;
      const target: Focusable | null | undefined = resolve ? resolve(container) : container;
      if (!target) return;
      if (target === container && !container.hasAttribute("tabindex")) {
        // Um contêiner só recebe foco programático se for focável.
        container.setAttribute("tabindex", "-1");
      }
      target.focus?.();
    }

    window.addEventListener("keydown", handleKeyDown);
    // Um frame de folga: o nó já está montado, mas o layout do react-native-web
    // ainda pode estar assentando quando o efeito corre.
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(focusInitial);
    } else {
      focusInitial();
    }

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [active, containerRef]);
}
