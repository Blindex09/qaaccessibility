from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.src.security.secret_store import (
    load_secrets_into_environment,
    migrate_plaintext_env_secrets,
)

_PROTECTED_ENV_NAMES = {
    "SECRET_KEY",
    "LLM_API_KEY",
    "CHAT_LLM_API_KEY",
    "LLM_FALLBACK_API_KEY",
    "FIRECRAWL_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "POSTMAN_API_KEY",
    "CYPRESS_RECORD_KEY",
    "GITHUB_TOKEN",
    "JIRA_API_TOKEN",
    "AZURE_DEVOPS_PAT",
    "BROWSERLESS_WS_URL",
    "WEBHOOK_SECRET",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "QA_API_TOKEN",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Multi-provider LLM settings.
    # Vazio por padrão: o usuário escolhe provider + chave na tela de
    # Configurações (nenhum provider e assumido sem configuração explicita).
    llm_provider: str = Field(
        default="",
        description="Provedor de LLM: openai, gemini, anthropic, xai, ollama-cloud",
    )
    llm_api_key: str | None = Field(default=None, description="Chave de API para o provedor")
    llm_base_url: str | None = Field(default=None, description="URL base para o provedor")
    llm_model: str | None = Field(default=None, description="ID do modelo para o provedor")

    # Firecrawl
    firecrawl_api_key: str | None = Field(default=None, description="Chave de API do Firecrawl para crawl de sites online")

    # Browserless
    browserless_ws_url: str | None = Field(default=None, description="URL do WebSocket do Browserless para rendering/screenshots na nuvem")

    # Busca web (chat)
    tavily_api_key: str | None = Field(default=None, description="Chave de API do Tavily para busca web no chat")
    exa_api_key: str | None = Field(default=None, description="Chave de API do Exa para busca web no chat")

    # Failover opcional — provider/modelo de reserva acionado pelo AIAgent quando
    # o primario falha. Inerte (None) se não configurado: comportamento inalterado.
    llm_fallback_provider: str | None = Field(default=None, description="Provedor de reserva para failover")
    llm_fallback_model: str | None = Field(default=None, description="Modelo de reserva para failover")
    llm_fallback_api_key: str | None = Field(default=None, description="Chave de API do provedor de reserva")
    llm_fallback_base_url: str | None = Field(default=None, description="URL base do provedor de reserva")

    # Backend
    backend_host: str = Field(default="127.0.0.1")
    backend_port: int = Field(default=8001)
    debug: bool = Field(default=False)
    # URL pública que o NAVEGADOR do usuário usa para baixar arquivos gerados
    # pelo backend (ZIP de correções, XLSX) -- ver `public_base_url()`. Nunca
    # assuma que backend_host/backend_port bastam: em qualquer deploy atrás de
    # proxy reverso/domínio real, o host que o processo escuta (127.0.0.1) não
    # é o host que o navegador consegue alcançar. Achado real: os 3 pontos que
    # geravam link de download tinham "http://localhost:8001" hardcoded no
    # código -- funcionava só em dev local, quebrava em qualquer outro ambiente.
    public_base_url: str | None = Field(
        default=None,
        description="URL pública do backend para links de download (ex.: https://api.meudominio.com). "
        "Sem isso, cai em http://{backend_host}:{backend_port} (correto só em dev local).",
    )

    # CORS
    allowed_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://localhost:8081",
            "http://127.0.0.1:8081",
            "http://localhost:19006",
            "http://127.0.0.1:19006",
            "http://localhost:19000",
            "http://127.0.0.1:19000",
        ],
    )

    # Seguranca
    secret_key: str = Field(..., description="Chave secreta da aplicacao — obrigatório em producao")
    qa_api_token: str | None = Field(
        default=None,
        description="Token opcional exigido nas rotas privadas da API local",
    )

    # Upload
    max_upload_size_mb: int = Field(default=10)
    upload_dir: str = Field(default="./uploads")

    # Orquestracao de sub-agentes — espelha o padrão de delegacao em
    # tools/delegate_tool.py (delegation.max_concurrent_children, default 3).
    # Os especialistas rodam em ONDAS de N concorrentes, em vez de todos de
    # uma vez, para não estourar o RPM do provider (cada filho consome a chave
    # de forma independente). Failover (provider de reserva) e feito pelo
    # AIAgent quando LLM_FALLBACK_* esta configurado. Retry/backoff exponencial
    # em erro transitorio (conexao, timeout, 429, 5xx) vem de graca dos SDKs
    # oficiais (openai/anthropic/google-genai), que ja retentam por padrao
    # (2-5x conforme o SDK) antes da excecao chegar aqui -- run_agent.py nao
    # duplica isso de proposito: ha um bug conhecido de stackar retry proprio
    # sobre o do SDK, multiplicando o tempo de espera em travamentos
    # silenciosos (auditoria 2026-08-01). Ver agent_timeout_seconds abaixo
    # para o teto total de espera.
    a11y_max_concurrent_agents: int = Field(
        default=3,
        ge=1,
        description="Maximo de sub-agentes de análise rodando em paralelo (default 3 para evitar limites de taxa de API)",
    )
    # Timeout por sub-agente. run_agent.AIAgent não implementa retry/backoff
    # próprio hoje — o valor generoso (180s) é para acomodar providers lentos
    # (ex.: Ollama Cloud) em uma única tentativa, não para sobreviver a retries.
    agent_timeout_seconds: float = Field(
        default=180.0,
        gt=0,
        description="Timeout wall-clock por sub-agente, em segundos (180s para acomodar providers lentos como Ollama Cloud)",
    )

    # Cache de respostas dos agentes de analise (exact-match, nao semantico --
    # ver response_cache.py). Evita custo/latencia duplicados quando a mesma
    # pagina e reanalisada sem alteracao dentro da janela de TTL. Nunca se
    # aplica a chat/tools (só aos 25 leaf subagents single-shot).
    a11y_response_cache_enabled: bool = Field(
        default=True,
        description="Cacheia respostas dos agentes de análise por hash exato do prompt (nunca em chat/tools)",
    )
    a11y_response_cache_ttl_seconds: float = Field(
        default=300.0,
        gt=0,
        description="TTL do cache de respostas dos agentes de análise, em segundos",
    )

    # Chat agentico (com tools/tool-loop) — provider que suporta o round-trip
    # multi-turn: OpenAI, Anthropic, Gemini, xAI, Ollama Cloud. Se não
    # configurado, cai no llm_* principal.
    chat_llm_provider: str | None = Field(default=None, description="Provider do chat agentico")
    chat_llm_model: str | None = Field(default=None, description="Modelo do chat agentico")
    chat_llm_api_key: str | None = Field(default=None, description="API key do chat agentico")
    chat_llm_base_url: str | None = Field(default=None, description="Base URL do chat agentico")

    def resolved_public_base_url(self) -> str:
        """Base URL para montar links de download voltados ao navegador do usuário.
        `public_base_url` configurado explicitamente vence sempre; sem ele, cai em
        `backend_host:backend_port` (só correto quando backend e navegador estão
        na mesma máquina -- dev local)."""
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        return f"http://{self.backend_host}:{self.backend_port}"

    def chat_model_config(self) -> dict[str, str | None]:
        """Resolve a config do chat, com fallback para o llm_* principal."""
        return {
            "provider": self.chat_llm_provider or self.llm_provider,
            "model": self.chat_llm_model or self.llm_model or "alto",
            "api_key": self.chat_llm_api_key or self.llm_api_key,
            "base_url": self.chat_llm_base_url or self.llm_base_url,
        }

    def build_fallback_model(self) -> dict[str, str] | None:
        """
        Monta o dict de failover no formato esperado pelo AIAgent
        (provider + model obrigatórios). Retorna None se não configurado,
        mantendo o comportamento sem failover.
        """
        if not (self.llm_fallback_provider and self.llm_fallback_model):
            return None
        fallback: dict[str, str] = {
            "provider": self.llm_fallback_provider,
            "model": self.llm_fallback_model,
        }
        if self.llm_fallback_api_key:
            fallback["api_key"] = self.llm_fallback_api_key
        if self.llm_fallback_base_url:
            fallback["base_url"] = self.llm_fallback_base_url
        return fallback


@lru_cache
def get_settings() -> Settings:
    for env_path in (Path(".env"), Path("backend/.env")):
        migrate_plaintext_env_secrets(env_path, _PROTECTED_ENV_NAMES)
    load_secrets_into_environment()
    return Settings()  # type: ignore[call-arg]  # pydantic-settings populates required fields (secret_key) from env/.env at runtime
