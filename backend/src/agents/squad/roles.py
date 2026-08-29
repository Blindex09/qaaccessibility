"""Papéis de uma squad de produto focada exclusivamente em acessibilidade."""

from enum import StrEnum


class SquadRole(StrEnum):
    CLIENT = "client"
    PRODUCT_OWNER = "product_owner"
    SCRUM_MASTER = "scrum_master"
    ENGINEERING_MANAGER = "engineering_manager"
    TECH_LEAD = "tech_lead"
    DEVELOPER = "developer"
    QA_LEAD = "qa_lead"
    A11Y_SPECIALIST = "a11y_specialist"
    DOCUMENTATION = "documentation"
    RELEASE = "release"
