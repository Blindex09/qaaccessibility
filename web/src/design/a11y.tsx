import React from "react";
import { Text } from "react-native";

import { a11y } from "./tokens";

/**
 * Nome acessível que chega mesmo à árvore de acessibilidade no web.
 *
 * Por que isto existe: o padrão `<View accessibilityRole="text"
 * accessibilityLabel="...">` NÃO funciona no react-native-web. O mapa
 * `AccessibilityUtil/propsToAriaRole.js` traduz `text` para `null`, e a função
 * só devolve um role quando `inferredRole !== null` — ou seja, para `text` não
 * é emitido atributo `role` nenhum. Um `aria-label` num elemento genérico sem
 * role não é exposto pelos leitores de tela, portanto o rótulo era descartado
 * em silêncio: o elemento ficava mudo.
 *
 * A solução usada aqui é a mesma que já funciona no `App.tsx`: em vez de
 * depender de `aria-label`, escreve-se o texto a sério, visualmente escondido
 * mas presente no DOM, e esconde-se da árvore de acessibilidade o conteúdo
 * visual que ele substitui. Texto real não depende de resolução de role.
 */
export function ScreenReaderText({ children }: { children: React.ReactNode }) {
  return <Text style={a11y.srOnly}>{children}</Text>;
}

/**
 * Props que removem um nó da árvore de acessibilidade em web e em nativo.
 * Vive em `tokens.ts` (módulo puro, sem react-native) para poder ser testado
 * sem o preset do RN; reexportado aqui para quem já importa este módulo.
 */
export const hiddenFromAssistiveTech = a11y.hiddenFromAssistiveTech;
