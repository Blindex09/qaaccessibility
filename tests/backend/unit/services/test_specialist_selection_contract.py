import jsonschema
import pytest

from backend.src.services.chat_tools import _ANALYZE_PAGE_SCHEMA, _ANALYZE_SITE_SCHEMA


@pytest.mark.parametrize("tool", [_ANALYZE_PAGE_SCHEMA, _ANALYZE_SITE_SCHEMA])
def test_model_must_declare_specialists_instead_of_triggering_legacy_defaults(tool):
    schema = tool["parameters"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"pre_exec_msg": "Vou analisar."}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"pre_exec_msg": "Vou analisar.", "only_agents": []}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"pre_exec_msg": "Vou analisar.", "only_agents": ["invented"]}, schema)
    jsonschema.validate({"pre_exec_msg": "Vou analisar.", "only_agents": ["forms_a11y"]}, schema)


def test_catalog_retains_accessibility_specialists():
    candidates = _ANALYZE_PAGE_SCHEMA["parameters"]["properties"]["only_agents"]["items"]["enum"]
    assert len(candidates) == len(set(candidates)) == 29
    assert {"spatial_3d_xr", "web_components", "niche_domains", "component_contracts"} <= set(candidates)
