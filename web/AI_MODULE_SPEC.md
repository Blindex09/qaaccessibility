# AI_MODULE_SPEC — Web

## Responsabilidade
Interface React Native Web chat-first para o QA Accessibility. A tela principal é
um assistente agêntico de acessibilidade que conversa por streaming SSE, aceita
anexos e aciona as ferramentas do backend para analisar, corrigir e exportar
resultados. A segunda tela configura provider, chave de API, modelo e URL base.

## Telas

| Tela | Arquivo | Responsabilidade |
|------|---------|------------------|
| ChatScreen | `web/src/screens/ChatScreen.tsx` | Chat com streaming token-a-token, anexos, eventos de progresso dos agentes e respostas de esclarecimento |
| SettingsScreen | `web/src/screens/SettingsScreen.tsx` | Provider, chave de API, modelo `alto` ou modelo concreto, e Base URL opcional |

`web/App.tsx` faz a navegação simples entre `chat` e `settings`, define `lang="pt-BR"`,
mantém um skip link e anuncia mudanças de tela para tecnologias assistivas.

## Serviços e hooks

| Módulo | Responsabilidade |
|--------|------------------|
| `web/src/hooks/useChat.ts` | Estado do chat, histórico, eventos SSE, anexos, clarify e o texto da live region (`announcement`) |
| `web/src/hooks/useDialogFocus.ts` | Padrão WAI-ARIA Dialog partilhado para modais que realmente precisam de foco isolado, como a chave de API. Não é usado pelo live preview persistente nem pelo pedido de aprovação inline. |
| `web/src/services/chat.ts` | Cliente `fetch` para `/chat/stream`, `/chat/clarify` e `/models` |
| `web/src/services/api.ts` | Cliente Axios para `/settings/` |
| `web/src/design/tokens.ts` | Tokens visuais e helpers de acessibilidade compartilhados |
| `web/src/design/helpers.ts` | Helpers de fonte/display usados pelas telas |

## Contrato de streaming

`streamChat()` consome eventos SSE enviados por `POST /chat/stream`:

| Evento | Uso na UI |
|--------|-----------|
| `token` | Acrescenta texto à resposta do assistente |
| `tool_start` / `tool_result` | Mostra início/fim de ferramentas |
| `phase` | Mostra fases do orchestrator |
| `agent` | Mostra início/fim de sub-agentes e quantidade de issues |
| `squad_plan` | Mostra no chat o plano, as tarefas, dependências e portões da squad de acessibilidade |
| `clarify` | Mostra o pedido do agente e envia a resposta via `/chat/clarify`. O botão que envia resposta vazia **nega** a ação (fail-closed no backend), por isso é rotulado "Cancelar" |
| `done` | Finaliza a resposta e anuncia a resposta final completa uma vez |
| `error` | Exibe erro acessível e anuncia a falha |

## Acessibilidade do chat

- **O balão do assistente nunca é live region.** Ele cresce token a token; um
  `aria-live` ali dispararia a cada delta e tornaria a resposta impossível de
  ouvir. Quem avisa que a resposta chegou é um anúncio único no fim do stream
  pelo único anunciador persistente, que é limpo depois da fala.
- **As live regions estão sempre montadas**, mesmo vazias, e ficam fora do fluxo
  quando não têm texto. Um leitor de ecrã só observa regiões que já existiam no
  DOM antes de o conteúdo mudar; uma região inserida junto com o seu texto é
  anunciada de forma pouco fiável em NVDA/JAWS. Existe apenas uma, reservada a
  “Digitando...” e à resposta final. Atividade, ferramentas e cronômetro ficam
  escritos e navegáveis, mas fora de regiões vivas.
  e anúncios do turno.
- **O anúncio é limpo antes de ser reescrito.** Uma live region só fala quando o
  texto muda, e as frases repetem-se em todos os turnos.
- **`ClarifyPanel` trata cada `view.kind` como conteúdo inline do chat:** aprovação,
  plano e pergunta usam `role="region"`, sem `aria-modal` e sem roubar o foco.
  Os botões Aprovar/Cancelar continuam disponíveis no próprio conteúdo da conversa.
- **`LivePreviewModal` mantém o nome histórico do componente, mas visualmente é um
  painel persistente `role="complementary"` no lado direito.** Ele abre
  automaticamente quando o backend/assistente emite a instrução de preview, não é
  um diálogo e contém iframe navegável com as versões original e corrigida. Ao
  iniciar outra auditoria, a sessão anterior é limpa e o painel passa a representar
  somente a nova página.

## Base URL

`BASE_URL` vem de `EXPO_PUBLIC_API_URL`; quando ausente, usa o host atual na porta
`8001`. O frontend/proxy local roda em `3000` e o backend local em `8001`.

## Invariantes

- Nenhum segredo ou API key fica hardcoded no frontend.
- O catálogo de modelos vem ao vivo de `/models`; listas locais não devem congelar modelos.
- O modelo padrão é `alto`, resolvido pelo backend via `agent/models_dev.py` (catálogo local).
- Toda mensagem de erro visível deve ser anunciável por leitor de tela.
- Imports ficam no topo do arquivo.
