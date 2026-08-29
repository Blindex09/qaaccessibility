import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.src.config.settings import get_settings
from backend.src.security.dependencies import rate_limit_dependency
from backend.src.security.secret_store import delete_secret, save_secret

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/settings",
    tags=["settings"],
)


def _reject_newlines(value: str, field_name: str) -> str:
    """Rejects embedded newlines/carriage returns before a value is written into a
    `KEY=value` line of the .env file. Without this, a value like
    "openai\\nGITHUB_TOKEN=attacker-controlled" injects arbitrary extra env-var lines
    into .env (and, via os.environ mirroring, into the running process) -- values here
    are only ever supposed to be single-line."""
    if "\n" in value or "\r" in value:
        raise HTTPException(
            status_code=400,
            detail=f"O campo '{field_name}' não pode conter quebras de linha.",
        )
    return value


class SettingsResponse(BaseModel):
    llm_provider: str
    llm_model: str | None
    llm_base_url: str | None
    has_llm_api_key: bool
    # Overrides opcionais do LLM usado especificamente pelo chat agêntico
    # (ChatScreen) -- quando ausentes, o chat cai de volta nos llm_* acima
    # (ver Settings.chat_llm_config em backend/src/config/settings.py).
    chat_llm_provider: str | None
    chat_llm_model: str | None
    chat_llm_base_url: str | None
    has_chat_llm_api_key: bool


class SettingsUpdateBody(BaseModel):
    llm_provider: str
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    chat_llm_provider: str | None = None
    chat_llm_api_key: str | None = None
    chat_llm_model: str | None = None
    chat_llm_base_url: str | None = None


@router.get("", response_model=SettingsResponse)
@router.get("/", response_model=SettingsResponse)
async def get_settings_route() -> SettingsResponse:
    settings = get_settings()
    return SettingsResponse(
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        llm_base_url=settings.llm_base_url,
        has_llm_api_key=bool(settings.llm_api_key),
        chat_llm_provider=settings.chat_llm_provider,
        chat_llm_model=settings.chat_llm_model,
        chat_llm_base_url=settings.chat_llm_base_url,
        has_chat_llm_api_key=bool(settings.chat_llm_api_key),
    )


@router.post("")
@router.post("/")
async def update_settings_route(body: SettingsUpdateBody) -> dict:
    env_path = "backend/.env"
    if not os.path.exists(env_path):
        env_path = ".env"

    _reject_newlines(body.llm_provider, "llm_provider")
    if body.llm_api_key is not None:
        _reject_newlines(body.llm_api_key, "llm_api_key")
    if body.llm_model is not None:
        _reject_newlines(body.llm_model, "llm_model")
    if body.llm_base_url is not None:
        _reject_newlines(body.llm_base_url, "llm_base_url")
    if body.chat_llm_provider is not None:
        _reject_newlines(body.chat_llm_provider, "chat_llm_provider")
    if body.chat_llm_api_key is not None:
        _reject_newlines(body.chat_llm_api_key, "chat_llm_api_key")
    if body.chat_llm_model is not None:
        _reject_newlines(body.chat_llm_model, "chat_llm_model")
    if body.chat_llm_base_url is not None:
        _reject_newlines(body.chat_llm_base_url, "chat_llm_base_url")

    logger.info("[Settings] Atualizando configs do LLM. Provider=%s, Model=%s", body.llm_provider, body.llm_model)

    # Ler linhas existentes
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if not line.endswith("\n"):
                    line += "\n"
                env_lines.append(line)

    # Mapeamento chave/valor
    env_vars = {}
    for line in env_lines:
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("#"):
            continue
        if "=" in line_strip:
            k, v = line_strip.split("=", 1)
            key = k.strip()
            if key not in {"LLM_API_KEY", "CHAT_LLM_API_KEY"}:
                env_vars[key] = v.strip()

    # Atualiza chaves com base no body
    env_vars["LLM_PROVIDER"] = body.llm_provider

    if body.llm_api_key is not None:
        val = body.llm_api_key.strip()
        if val and "•" not in val:
            save_secret("LLM_API_KEY", val)
        elif not val:
            delete_secret("LLM_API_KEY")

    if body.llm_model is not None:
        env_vars["LLM_MODEL"] = body.llm_model.strip()

    if body.llm_base_url is not None:
        env_vars["LLM_BASE_URL"] = body.llm_base_url.strip()

    if body.chat_llm_provider is not None:
        val = body.chat_llm_provider.strip()
        if val:
            env_vars["CHAT_LLM_PROVIDER"] = val
        elif "CHAT_LLM_PROVIDER" in env_vars:
            del env_vars["CHAT_LLM_PROVIDER"]

    if body.chat_llm_api_key is not None:
        val = body.chat_llm_api_key.strip()
        if val and "•" not in val:
            save_secret("CHAT_LLM_API_KEY", val)
        elif not val:
            delete_secret("CHAT_LLM_API_KEY")

    if body.chat_llm_model is not None:
        val = body.chat_llm_model.strip()
        if val:
            env_vars["CHAT_LLM_MODEL"] = val
        elif "CHAT_LLM_MODEL" in env_vars:
            del env_vars["CHAT_LLM_MODEL"]

    if body.chat_llm_base_url is not None:
        val = body.chat_llm_base_url.strip()
        if val:
            env_vars["CHAT_LLM_BASE_URL"] = val
        elif "CHAT_LLM_BASE_URL" in env_vars:
            del env_vars["CHAT_LLM_BASE_URL"]

    # Regrava preservando linhas de comentarios e atualizando valores em linha
    new_lines = []
    written_keys = set()
    for line in env_lines:
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in line_strip:
            k, _ = line_strip.split("=", 1)
            key_strip = k.strip()
            if key_strip in env_vars:
                new_lines.append(f"{key_strip}={env_vars[key_strip]}\n")
                written_keys.add(key_strip)
            else:
                deletable_keys = {
                    "LLM_API_KEY",
                    "CHAT_LLM_PROVIDER",
                    "CHAT_LLM_API_KEY",
                    "CHAT_LLM_MODEL",
                    "CHAT_LLM_BASE_URL",
                }
                if key_strip in deletable_keys and key_strip not in env_vars:
                    continue
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Escreve chaves que não existiam no .env original
    for k, v in env_vars.items():
        if k not in written_keys:
            new_lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Aplica no ambiente do processo para que BaseSettings (prioriza os.environ)
    # leia o valor novo sem precisar reiniciar o servidor.
    os.environ["LLM_PROVIDER"] = body.llm_provider
    if body.llm_api_key is not None:
        val = body.llm_api_key.strip()
        if val and "•" not in val:
            os.environ["LLM_API_KEY"] = val
        elif not val and "LLM_API_KEY" in os.environ:
            del os.environ["LLM_API_KEY"]
    if body.llm_model is not None:
        os.environ["LLM_MODEL"] = body.llm_model.strip()
    if body.llm_base_url is not None:
        os.environ["LLM_BASE_URL"] = body.llm_base_url.strip()
    if body.chat_llm_provider is not None:
        val = body.chat_llm_provider.strip()
        if val:
            os.environ["CHAT_LLM_PROVIDER"] = val
        elif "CHAT_LLM_PROVIDER" in os.environ:
            del os.environ["CHAT_LLM_PROVIDER"]
    if body.chat_llm_api_key is not None:
        val = body.chat_llm_api_key.strip()
        if val and "•" not in val:
            os.environ["CHAT_LLM_API_KEY"] = val
        elif not val and "CHAT_LLM_API_KEY" in os.environ:
            del os.environ["CHAT_LLM_API_KEY"]
    if body.chat_llm_model is not None:
        val = body.chat_llm_model.strip()
        if val:
            os.environ["CHAT_LLM_MODEL"] = val
        elif "CHAT_LLM_MODEL" in os.environ:
            del os.environ["CHAT_LLM_MODEL"]
    if body.chat_llm_base_url is not None:
        val = body.chat_llm_base_url.strip()
        if val:
            os.environ["CHAT_LLM_BASE_URL"] = val
        elif "CHAT_LLM_BASE_URL" in os.environ:
            del os.environ["CHAT_LLM_BASE_URL"]

    # Limpa cache do get_settings e sincroniza as configurações ativas no llm_client
    get_settings.cache_clear()
    from backend.src.services.llm_client import refresh_settings

    refresh_settings()
    return {"status": "ok"}


class ServiceKeyUpdateBody(BaseModel):
    service_name: str  # ex.: 'postman', 'cypress_record_key', 'cypress_project_id', 'github_token', 'tavily', 'exa', 'browserless'
    api_key: str


@router.post("/service-key", dependencies=[Depends(rate_limit_dependency)])
async def update_service_key_route(body: ServiceKeyUpdateBody) -> dict:
    """
    Atualiza uma credencial de serviço no cofre local protegido e no ambiente
    do processo. Credenciais nunca são gravadas no arquivo .env.
    """
    key_map = {
        "postman": "POSTMAN_API_KEY",
        "postman_api_key": "POSTMAN_API_KEY",
        "cypress_record_key": "CYPRESS_RECORD_KEY",
        "cypress_project_id": "CYPRESS_PROJECT_ID",
        "github_token": "GITHUB_TOKEN",
        "github": "GITHUB_TOKEN",
        "tavily": "TAVILY_API_KEY",
        "exa": "EXA_API_KEY",
        "browserless": "BROWSERLESS_WS_URL",
    }

    _reject_newlines(body.service_name, "service_name")
    _reject_newlines(body.api_key, "api_key")

    target_env_var = key_map.get(body.service_name.lower().strip())
    if target_env_var is None:
        raise HTTPException(
            status_code=400,
            detail="Serviço não permitido.",
        )
    val = body.api_key.strip()

    if not val:
        raise HTTPException(status_code=400, detail="A chave informada não pode ser vazia.")

    os.environ[target_env_var] = val
    save_secret(target_env_var, val)

    logger.info("[Settings] Chave de serviço %s atualizada em tempo de execução.", target_env_var)
    return {"status": "ok", "service": body.service_name, "env_var": target_env_var}
