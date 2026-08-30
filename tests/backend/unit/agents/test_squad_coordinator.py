from backend.src.agents.squad import SquadRole, build_squad_plan
from backend.src.agents.squad.contracts import TaskStatus


def test_squad_plan_is_accessibility_only_and_has_quality_gates():
    plan = build_squad_plan("Corrigir o conteúdo principal de uma página")

    assert plan.domain == "digital_accessibility"
    assert plan.tasks[0].role is SquadRole.PRODUCT_OWNER
    assert "não implementar sem aprovação explícita" in plan.quality_gates


def test_squad_plan_orders_analysis_fix_qa_and_documentation():
    plan = build_squad_plan("Auditar e corrigir uma URL")
    by_id = {task.id: task for task in plan.tasks}

    assert by_id["a11y-analysis"].depends_on == ["product-scope"]
    assert by_id["a11y-remediation"].depends_on == ["a11y-analysis"]
    # QA pende da análise, não da correção: auditoria sem correção aprovada
    # continua tendo validação e entrega.
    assert by_id["qa-validation"].depends_on == ["a11y-analysis"]
    assert by_id["documentation-release"].depends_on == ["qa-validation"]
    assert "live_preview_evidence" in by_id["qa-validation"].artifacts


# ── Regressão: o plano não pode depender de palavra-chave ─────────────────────
# Bug real: o chamador decidia por regex (`corrig|remedi|fix|implementar|
# aplicar`) se a etapa de correção entrava no plano. Pedidos de correção
# legítimos que não usam essas raízes chegavam ao modelo com um contrato de
# execução SEM etapa de correção -- e o plano vai para o prompt, então a regex
# condicionava a LLM, o que o README proíbe explicitamente.

_PEDIDOS = [
    "Corrija o contraste do cabeçalho",  # casaria com a regex antiga
    "melhore o contraste do cabeçalho",  # NÃO casaria
    "deixe essa página acessível",  # NÃO casaria
    "ajuste os rótulos dos botões",  # NÃO casaria
    "só me diga o que está errado, não mude nada",  # nem deveria casar
    "",  # mensagem vazia
]


def test_etapa_de_correcao_existe_qualquer_que_seja_a_frase_do_usuario():
    for pedido in _PEDIDOS:
        by_id = {t.id: t for t in build_squad_plan(pedido).tasks}
        assert "a11y-remediation" in by_id, f"plano sem etapa de correção para: {pedido!r}"


def test_correcao_nasce_bloqueada_por_aprovacao_em_qualquer_frase():
    for pedido in _PEDIDOS:
        by_id = {t.id: t for t in build_squad_plan(pedido).tasks}
        remediacao = by_id["a11y-remediation"]
        assert remediacao.status is TaskStatus.BLOCKED, pedido
        assert any("aprovação explícita" in c for c in remediacao.acceptance_criteria), pedido


def test_o_plano_e_identico_independentemente_da_frase():
    """Nenhum ramo do plano pode variar com o texto, só o campo `objective`."""
    planos = [build_squad_plan(p).to_dict() for p in _PEDIDOS]
    for plano in planos:
        plano.pop("objective")
    primeiro = planos[0]
    assert all(p == primeiro for p in planos[1:])


def test_build_squad_plan_nao_aceita_mais_o_flag_de_implementacao():
    """O parâmetro sumiu de propósito: era o que a regex alimentava."""
    import inspect

    assert "include_implementation" not in inspect.signature(build_squad_plan).parameters
