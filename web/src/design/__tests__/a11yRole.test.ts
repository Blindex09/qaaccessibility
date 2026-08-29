/* eslint-env jest, node */

// Build CJS: o `dist/` é ESM e o jest deste projeto não transforma node_modules.
// É o mesmo módulo, apenas noutro formato.
import propsToAriaRole from "react-native-web/dist/cjs/modules/AccessibilityUtil/propsToAriaRole";

import { a11y } from "../tokens";

const hiddenFromAssistiveTech = a11y.hiddenFromAssistiveTech;

/**
 * Este teste não procura strings no código-fonte: chama a função REAL do
 * react-native-web que decide que atributo `role` sai no DOM, e fixa o
 * comportamento que motivou o padrão em `design/a11y.tsx`.
 *
 * O bug: `<View accessibilityRole="text" accessibilityLabel="...">` parecia
 * correto e não produzia role nenhum, portanto o `aria-label` ficava num
 * elemento genérico — e um `aria-label` sem role não é exposto pelos leitores
 * de tela. O rótulo era descartado em silêncio. Se uma versão futura do
 * react-native-web passar a mapear `text` para um role real, este teste falha
 * e avisa que o contorno já não é necessário.
 */

describe("react-native-web — resolução de role (comportamento real da lib)", () => {
  test('accessibilityRole="text" não emite role nenhum', () => {
    expect(propsToAriaRole({ accessibilityRole: "text" })).toBeUndefined();
  });

  test('role="text" cru também não emite role: a lib usa o mesmo mapa', () => {
    // Descarta o contorno "passar role web cru": não funciona para `text`.
    expect(propsToAriaRole({ role: "text" })).toBeUndefined();
  });

  test("roles que a lib mapeia continuam saindo (controle do teste)", () => {
    expect(propsToAriaRole({ accessibilityRole: "button" })).toBe("button");
    expect(propsToAriaRole({ accessibilityRole: "header" })).toBe("heading");
    // Roles fora do mapa passam tal e qual — é assim que `main`/`banner`
    // funcionam no App.tsx.
    expect(propsToAriaRole({ role: "main" })).toBe("main");
  });

  test("sem role e sem accessibilityRole não há role", () => {
    expect(propsToAriaRole({})).toBeUndefined();
  });
});

describe("padrão de substituição", () => {
  test("hiddenFromAssistiveTech esconde o nó em web e em nativo", () => {
    // Web: aria-hidden. Nativo iOS: accessibilityElementsHidden.
    // Nativo Android: importantForAccessibility.
    expect(hiddenFromAssistiveTech["aria-hidden"]).toBe(true);
    expect(hiddenFromAssistiveTech.accessibilityElementsHidden).toBe(true);
    expect(hiddenFromAssistiveTech.importantForAccessibility).toBe("no-hide-descendants");
  });

  test("o nó escondido não depende de resolução de role", () => {
    // `aria-hidden` é honrado em qualquer elemento, com ou sem role — ao
    // contrário de `aria-label`, que foi o que falhou no padrão antigo.
    expect(propsToAriaRole(hiddenFromAssistiveTech as never)).toBeUndefined();
  });
});
