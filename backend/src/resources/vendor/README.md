# vendor/axe.min.js

Motor real de auditoria de acessibilidade [axe-core](https://github.com/dequelabs/axe-core)
(Deque Systems, MPL-2.0), vendorizado localmente para injeção via Playwright
(`axe_core_runner.py`) -- é o MESMO motor de detecção usado por `cypress-axe`,
`axe-playwright` e `axe-selenium-python`.

Vendorizado em vez de carregado por CDN em runtime para não depender de
conectividade externa/CDN-uptime a cada chamada de `run_remote_test` e para
fixar a versão (reprodutibilidade -- resultados não mudam entre execuções por
causa de uma atualização silenciosa do CDN).

- Versão atual: **4.13.0**
- Fonte: `https://unpkg.com/axe-core@4.13.0/axe.min.js`
- Para atualizar: baixar a nova versão da mesma URL (trocando o número da
  versão) e substituir este arquivo. Conferir o changelog oficial antes de
  atualizar em produção -- novas regras podem mudar a contagem de violações
  de análises já em andamento.
