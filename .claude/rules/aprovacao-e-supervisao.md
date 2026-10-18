---
paths:
  - "backend/**"
  - "web/src/**"
---

# Aprovação e supervisão humana (regras 7 e 16)

> Texto integral das regras 7 e 16, mais as decisões do dono de 17/out/2026 (no fim). A divergência antiga com a regra permanente de harness sobre ferramentas irreversíveis está resolvida: a chave de aprovação da pessoa vale para tudo.

### 7. Aprovação: ligada ou desligada, nunca bloqueio

- Com a aprovação desligada, o agente faz tudo sem perguntar. Com ela ligada, faz com pedido de aprovação. Nunca uma
  recusa seca. Vale para o sistema inteiro e para todas as interfaces.
- Ações irreversíveis ou de alto impacto (apagar, sobrescrever, enviar, publicar, gastar) seguem a configuração de
  aprovação.
- A confirmação mostra tudo o que vai mudar, inclusive o que seria desligado. Nunca desligar uma capacidade que ninguém
  pediu.
- A segurança existe, mas sem travas desnecessárias: o sistema é seguro e ao mesmo tempo livre.
- O que não entra na chave de aprovação são os limites do harness da regra 1, como a pasta de trabalho: o agente não
  mexe fora da pasta que a pessoa escolheu. A liberdade vem de a pessoa poder escolher qualquer pasta pela interface, e
  não de o agente sair dela sozinho.

### 16. Supervisão humana calibrada

- Intervenção humana onde o risco é maior (ações irreversíveis, escopo ampliado, ambiguidade material) e fora do
  caminho no resto. Supervisão constante em ação de baixo risco é tão errado quanto autonomia total em ação de alto
  risco.

## Decisões do dono de 17/out/2026

- Com a aprovação desligada pela pessoa, o agente segue tudo sem pedir aprovação, inclusive em ação irreversível. Ligada, pede. A aprovação é
  uma chave da pessoa; não existe ferramenta que a configuração não consiga soltar.
- Com a aprovação ligada, a aprovação vale para os argumentos exatos que foram mostrados: se os argumentos mudam depois do sim, a decisão
  anterior não vale e uma nova é pedida.
- Com a aprovação ligada, instalar software desconhecido (pacote, programa, servidor MCP, skill de terceiros) sempre pede aprovação, por risco de
  cadeia de suprimento. Com ela desligada, segue.
