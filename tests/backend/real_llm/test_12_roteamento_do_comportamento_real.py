"""
Camada 12 -- Roteamento da prova de comportamento (real).

A decisao de QUANDO provar o comportamento de uma pagina num navegador real (grupo `comportamento`, ferramenta `verify_page_behavior`, servidor MCP de
acessibilidade) e' do roteador, um modelo, pelo significado do pedido. O codigo so oferece o grupo. Este teste mede a decisao de verdade: um conjunto
rotulado de pedidos em que a prova de execucao EH necessaria e outro em que NAO eh (leitura de marcacao, contraste, documento, requisito, conceito,
conversa), cada um repetido para medir uma TAXA e nao uma execucao unica (regra 15: confianca medida, nunca presumida).

Os limites abaixo sao os primeiros numeros, escolhidos antes da primeira medicao: depois da primeira rodada ao vivo, registre as taxas medidas em
docs/modules/prova_de_comportamento_mcp.md e ajuste os limites a elas, nunca o contrario. Um pedido de fronteira (auditoria geral de uma pagina) fica
fora dos dois conjuntos de proposito: o agente pode habilitar o grupo depois, com a analise estatica na mao.
"""

import json
import os

import pytest

from backend.src.services.route_advisor import advise_route, clear_advisor_cache
from backend.src.services.tool_groups import GROUP_DESCRIPTIONS
from tests.backend.real_llm.conftest import REAL_PROVIDER, selected_key

pytestmark = pytest.mark.real_llm

TENTATIVAS = int(os.getenv("REAL_LLM_ROUTING_ATTEMPTS", "3"))
MINIMO_DE_ACERTO_NECESSARIO = 0.75  # pedidos que precisam da prova: o grupo deve ser escolhido em pelo menos isto das tentativas
MAXIMO_DE_ESCOLHA_SEM_NECESSIDADE = 0.15  # pedidos que nao precisam: o grupo nao deve ser escolhido em mais do que isto

PRECISA_DA_PROVA = [
    "O menu da minha página abre com o mouse, mas desconfio que não funciona só com o teclado. Teste de verdade em https://exemplo.test/loja e me diga.",
    "Corrigi o diálogo de confirmação. Confirma no navegador que o foco entra nele e volta para o botão que o abriu: https://exemplo.test/dialogo",
    "A análise disse que talvez o modal não prenda o foco. Verifica isso de verdade em https://exemplo.test/modal, não só olhando o código.",
    "Esse formulário mostra o erro, mas será que quem usa leitor de tela é avisado? Teste a página https://exemplo.test/cadastro",
    "As abas desta página respondem às setas, ao Home e ao End como deveriam? Quero ver o comportamento real em https://exemplo.test/abas",
    "Depois de clicar em Buscar a lista atualiza sozinha. Isso é anunciado para quem não vê a tela? Prove na página https://exemplo.test/busca",
    "Troquei de tela neste app de página única e o foco parece sumir. Reproduza em https://exemplo.test/app e diga o que acontece.",
    "Faça um passeio com a tecla Tab pela página inteira e diga se há armadilha de teclado: https://exemplo.test/",
]

NAO_PRECISA_DA_PROVA = [
    "O que é o critério 1.4.3 do WCAG?",
    "Gere o VPAT da última análise.",
    "Corrija o texto alternativo das imagens deste HTML: <img src='a.png'><img src='b.png' alt=''>",
    "Revise este requisito: ao excluir um item, o usuário abre uma janela para confirmar. Que riscos de acessibilidade eu devo prever?",
    "O contraste de um botão com texto #999999 sobre fundo branco passa no AA?",
    "Bom dia! Tudo bem?",
    "Abra um ticket no Jira para o problema de contraste que você achou.",
    "Audite o PDF que eu anexei.",
    "Qual a diferença entre aria-label e aria-labelledby?",
]


async def _grupos_escolhidos(pedido: str) -> list[str]:
    clear_advisor_cache()  # sem cache de decisao: cada tentativa consulta o modelo de novo
    advice = await advise_route(
        REAL_PROVIDER, "alto", task=json.dumps({"history": [], "message": pedido}, ensure_ascii=False), step_type="chat",
        api_key=selected_key(REAL_PROVIDER), base_url=None, output_tokens=16384, needs_tools=True, tool_catalog=GROUP_DESCRIPTIONS,
    )
    return list(advice.tool_groups or [])


async def _taxa(pedidos: list[str]) -> tuple[float, dict[str, int]]:
    por_pedido: dict[str, int] = {}
    for pedido in pedidos:
        por_pedido[pedido] = sum("comportamento" in await _grupos_escolhidos(pedido) for _ in range(TENTATIVAS))
    return sum(por_pedido.values()) / (len(pedidos) * TENTATIVAS), por_pedido


@pytest.mark.asyncio
async def test_roteador_escolhe_o_grupo_quando_a_resposta_depende_do_que_acontece_em_execucao(alto_model_id: str) -> None:
    taxa, por_pedido = await _taxa(PRECISA_DA_PROVA)
    print(f"\n[roteamento comportamento] modelo={alto_model_id} tentativas={TENTATIVAS} taxa de escolha quando PRECISA={taxa:.2f}")
    for pedido, n in por_pedido.items():
        print(f"  {n}/{TENTATIVAS}  {pedido[:90]}")
    assert taxa >= MINIMO_DE_ACERTO_NECESSARIO, por_pedido


@pytest.mark.asyncio
async def test_roteador_nao_escolhe_o_grupo_quando_ler_o_codigo_ou_responder_resolve(alto_model_id: str) -> None:
    taxa, por_pedido = await _taxa(NAO_PRECISA_DA_PROVA)
    print(f"\n[roteamento comportamento] modelo={alto_model_id} tentativas={TENTATIVAS} taxa de escolha quando NAO PRECISA={taxa:.2f}")
    for pedido, n in por_pedido.items():
        print(f"  {n}/{TENTATIVAS}  {pedido[:90]}")
    assert taxa <= MAXIMO_DE_ESCOLHA_SEM_NECESSIDADE, por_pedido
