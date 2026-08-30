"""Agentes de papel da squad de acessibilidade.

Um módulo por papel, com uma responsabilidade cada e sem sobreposição -- é o
que separa uma squad de um agente só com muitos prompts. A execução é
compartilhada em `_runner.py` para que a separação seja de RESPONSABILIDADE,
não de código duplicado.

Papéis que já existiam como agente do pipeline NÃO são reimplementados aqui
(regra de zero duplicação do README):

    Developer        -> `fixer`
    A11y Specialist  -> `a11y_expert_reviewer`
    Documentation    -> `checklist`, `reporter`, `vpat_reporter`
    Client           -> o próprio usuário, não um agente
"""

from .engineering_manager import run_engineering_manager
from .product_owner import run_product_owner
from .qa_lead import run_qa_lead
from .release_manager import run_release
from .scrum_master import run_scrum_master
from .tech_lead import run_tech_lead

__all__ = [
    "run_engineering_manager",
    "run_product_owner",
    "run_qa_lead",
    "run_release",
    "run_scrum_master",
    "run_tech_lead",
]
