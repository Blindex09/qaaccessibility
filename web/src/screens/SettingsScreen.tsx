import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  Platform,
} from "react-native";
import { getSettings, saveSettings, saveServiceKey, SettingsData } from "../services/api";
import { getModels } from "../services/chat";
import { colors, font, radius, space, shadow, a11y } from "../design/tokens";
import { displayFont, monoFont } from "../design/helpers";

// Providers suportados (tool-capable, espelham CHAT_PROVIDERS do backend).
// A ORDEM aqui é idêntica à do backend (models_route.py) — "agentic" (lógico)
// vem primeiro como opção recomendada, seguido dos 5 providers concretos.
const PROVIDERS = [
  { id: "agentic", label: "Agentic Auto (Seleção Inteligente)", placeholderUrl: "" },
  { id: "openai", label: "OpenAI", placeholderUrl: "https://api.openai.com/v1" },
  { id: "anthropic", label: "Anthropic", placeholderUrl: "https://api.anthropic.com" },
  { id: "gemini", label: "Gemini", placeholderUrl: "https://generativelanguage.googleapis.com" },
  { id: "xai", label: "xAI (Grok)", placeholderUrl: "https://api.x.ai/v1" },
  { id: "ollama-cloud", label: "Ollama Cloud", placeholderUrl: "https://ollama.com/v1" },
];

interface Props {
  onBack: () => void;
}

const PROVIDER_IDS = ["agentic", "openai", "anthropic", "gemini", "xai", "ollama-cloud"];

// Chaves de serviços de terceiros, salvas via POST /settings/service-key
// (write-only: o backend nunca as devolve pelo GET /settings, só confirma
// o env var atualizado).
const THIRD_PARTY_SERVICES = [
  { id: "postman", label: "Postman API Key", placeholder: "PMAK-..." },
  { id: "cypress_record_key", label: "Cypress Record Key", placeholder: "Chave de gravação do Cypress Cloud" },
  { id: "cypress_project_id", label: "Cypress Project ID", placeholder: "ID do projeto no Cypress Cloud" },
  { id: "github_token", label: "GitHub Token", placeholder: "ghp_..." },
  { id: "tavily", label: "Tavily API Key", placeholder: "tvly-..." },
  { id: "exa", label: "Exa API Key", placeholder: "Chave de API do Exa" },
  { id: "browserless", label: "Browserless WS URL", placeholder: "wss://chrome.browserless.io?token=..." },
];

// Catálogo de modelos por provider vem AO VIVO do backend (/models →
// models.dev via Hermes); nada hardcoded que envelhece. Ver state
// `providerModels` carregado no componente.


export function SettingsScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Refs de acessibilidade para roving tabindex
  const agenticRef = React.useRef<any>(null);
  const openaiRef = React.useRef<any>(null);
  const geminiRef = React.useRef<any>(null);
  const anthropicRef = React.useRef<any>(null);
  const xaiRef = React.useRef<any>(null);
  const ollamaCloudRef = React.useRef<any>(null);

  const providerRefs = {
    agentic: agenticRef,
    openai: openaiRef,
    gemini: geminiRef,
    anthropic: anthropicRef,
    xai: xaiRef,
    "ollama-cloud": ollamaCloudRef,
  };

  // Form State
  const [provider, setProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [selectedModelOption, setSelectedModelOption] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  // Loaded metadata
  const [hasApiKey, setHasApiKey] = useState(false);
  const [initialProvider, setInitialProvider] = useState("");
  const [initialHasApiKey, setInitialHasApiKey] = useState(false);
  // Catálogo por provider AO VIVO (/models → models.dev via Hermes), já sem o
  // sentinela "alto" (renderizado à parte). Vazio quando o backend está offline.
  const [providerModels, setProviderModels] = useState<Record<string, string[]>>({});
  const [modelCapabilities, setModelCapabilities] = useState<Record<string, Record<string, any>>>({});

  // Overrides opcionais do LLM usado pelo chat agêntico (ChatScreen). Quando
  // vazios, o chat usa o provider/modelo/chave principais configurados acima.
  const [chatLlmEnabled, setChatLlmEnabled] = useState(false);
  const [chatLlmProvider, setChatLlmProvider] = useState("");
  const [chatLlmApiKey, setChatLlmApiKey] = useState("");
  const [chatLlmModel, setChatLlmModel] = useState("");
  const [chatLlmBaseUrl, setChatLlmBaseUrl] = useState("");
  const [hasChatLlmApiKey, setHasChatLlmApiKey] = useState(false);

  // Chaves de serviços de terceiros (Postman, Cypress, GitHub, Tavily, Exa,
  // Browserless) -- write-only via /settings/service-key, um campo por serviço.
  const [serviceKeyValues, setServiceKeyValues] = useState<Record<string, string>>({});
  const [serviceKeySaving, setServiceKeySaving] = useState<string | null>(null);
  const [serviceKeyStatus, setServiceKeyStatus] = useState<Record<string, string>>({});

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const data = await getSettings();

        // Modelos atuais por provider (sem listas hardcoded que envelhecem).
        let liveModels: Record<string, string[]> = {};
        try {
          const list = await getModels();
          liveModels = Object.fromEntries(
            list.map((p) => [p.id, p.models.filter((m) => m !== "alto")]),
          );
          setProviderModels(liveModels);
          setModelCapabilities(Object.fromEntries(
            list.map((p) => [p.id, p.model_capabilities || {}]),
          ));
        } catch {
          /* backend offline — só "Alto" + modelo customizado ficam disponíveis */
        }

        const loadedProvider = data.llm_provider || "openai";
        const providerSupported = PROVIDER_IDS.includes(loadedProvider);
        const currentProvider = providerSupported ? loadedProvider : "openai";
        setProvider(currentProvider);
        setInitialProvider(currentProvider);

        // Se o provider salvo não é mais suportado (provider legado fora dos 5
        // nativos), o modelo salvo pertence a ele — descartamos e voltamos ao "Alto".
        const loadedModel = providerSupported ? (data.llm_model || "") : "";
        const modelsList = liveModels[currentProvider] || [];
        if (!loadedModel || loadedModel.toLowerCase() === "alto") {
          // Padrão "Alto": o backend escolhe o melhor modelo do provider.
          setModel("alto");
          setSelectedModelOption("alto");
        } else if (modelsList.includes(loadedModel)) {
          setModel(loadedModel);
          setSelectedModelOption(loadedModel);
        } else {
          setModel(loadedModel);
          setSelectedModelOption("custom");
        }

        setBaseUrl(data.llm_base_url || "");
        setHasApiKey(data.has_llm_api_key);
        setInitialHasApiKey(data.has_llm_api_key);

        // Se já tem chave cadastrada, mostramos uma máscara no input para sinalizar
        if (data.has_llm_api_key) {
          setApiKey("••••••••••••••••••••••••");
        }

        // Overrides do chat: só ativamos a seção se já houver algo configurado.
        const hasChatOverride = !!(data.chat_llm_provider || data.has_chat_llm_api_key);
        setChatLlmEnabled(hasChatOverride);
        setChatLlmProvider(data.chat_llm_provider || "");
        setChatLlmModel(data.chat_llm_model || "");
        setChatLlmBaseUrl(data.chat_llm_base_url || "");
        setHasChatLlmApiKey(!!data.has_chat_llm_api_key);
        if (data.has_chat_llm_api_key) {
          setChatLlmApiKey("••••••••••••••••••••••••");
        }
      } catch {
        setErrorMsg("Falha ao carregar configurações do backend.");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  async function handleSave() {
    setSaving(true);
    setStatusMsg(null);
    setErrorMsg(null);

    const payload: Partial<SettingsData> = {
      llm_provider: provider,
      llm_model: model,
      llm_base_url: baseUrl,
    };

    // Só envia a chave de API se o usuário alterou o valor da máscara padrão
    if (apiKey && apiKey !== "••••••••••••••••••••••••") {
      payload.llm_api_key = apiKey;
    } else if (!apiKey) {
      // Se limpou o campo, removemos a chave
      payload.llm_api_key = "";
    }

    // Overrides do chat: se a seção estiver desativada, envia campos vazios
    // para limpar qualquer override anterior; senão, envia os valores atuais.
    payload.chat_llm_provider = chatLlmEnabled ? chatLlmProvider : "";
    payload.chat_llm_model = chatLlmEnabled ? chatLlmModel : "";
    payload.chat_llm_base_url = chatLlmEnabled ? chatLlmBaseUrl : "";
    if (chatLlmEnabled && chatLlmApiKey && chatLlmApiKey !== "••••••••••••••••••••••••") {
      payload.chat_llm_api_key = chatLlmApiKey;
    } else if (!chatLlmEnabled || !chatLlmApiKey) {
      payload.chat_llm_api_key = "";
    }

    try {
      await saveSettings(payload);
      setHasApiKey(!!apiKey);
      setHasChatLlmApiKey(chatLlmEnabled && !!chatLlmApiKey);
        setStatusMsg("Configurações salvas! Voltando para a tela inicial…");
      // Anuncia o sucesso (live region) e então fecha, voltando para a home.
      setTimeout(() => onBack(), 1200);
    } catch {
      setErrorMsg("Ocorreu um erro ao salvar as configurações.");
      setSaving(false);
    }
  }

  // Preenche valores recomendados ao selecionar um provider.
  // O modelo padrão e sempre "Alto": o backend roteia para o melhor modelo
  // recente e com ferramentas do provider, entao o usuário so escolhe o
  // provider e a chave de API.
  function handleSelectProvider(provId: string) {
    setProvider(provId);
    // NÃO força base_url: o Hermes já conhece o endpoint correto de cada provider
    // (ex.: Ollama Cloud = https://ollama.com/v1). Deixamos vazio para o Hermes
    // resolver; o campo Base URL fica como override avançado opcional.
    setBaseUrl("");
    setModel("alto");
    setSelectedModelOption("alto");

    if (provId === initialProvider) {
      setHasApiKey(initialHasApiKey);
      setApiKey(initialHasApiKey ? "••••••••••••••••••••••••" : "");
    } else {
      setHasApiKey(false);
      setApiKey("");
    }
  }

  async function handleSaveServiceKey(serviceId: string) {
    const value = (serviceKeyValues[serviceId] || "").trim();
    if (!value) return;
    setServiceKeySaving(serviceId);
    setServiceKeyStatus((s) => ({ ...s, [serviceId]: "" }));
    try {
      await saveServiceKey(serviceId, value);
      setServiceKeyStatus((s) => ({ ...s, [serviceId]: "Chave salva com sucesso." }));
      setServiceKeyValues((v) => ({ ...v, [serviceId]: "" }));
    } catch {
      setServiceKeyStatus((s) => ({ ...s, [serviceId]: "Erro ao salvar a chave." }));
    } finally {
      setServiceKeySaving(null);
    }
  }

  // Manipulador de setas do teclado (roving tabindex) para rádio do provider
  const handleKeyDown = (e: any, currentId: string) => {
    const currentIndex = PROVIDER_IDS.indexOf(currentId);
    let nextIndex = currentIndex;

    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % PROVIDER_IDS.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      nextIndex = (currentIndex - 1 + PROVIDER_IDS.length) % PROVIDER_IDS.length;
    } else {
      return; // Outras teclas seguem comportamento padrão
    }

    const nextId = PROVIDER_IDS[nextIndex];
    handleSelectProvider(nextId);

    // Roving focus após o render do estado
    setTimeout(() => {
      const ref = providerRefs[nextId as keyof typeof providerRefs];
      if (ref && ref.current) {
        ref.current.focus();
      }
    }, 50);
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.accent.DEFAULT} />
        <Text 
          style={styles.loadingText} 
          accessibilityLiveRegion="polite"
          accessibilityRole={"status" as any}
          role="status"
        >
          Carregando configurações…
        </Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
      {/* Top Bar */}
      <View style={styles.topBar}>
        <TouchableOpacity
          onPress={onBack}
          style={styles.backBtn}
          accessibilityRole="button"
          accessibilityLabel="Voltar para a tela inicial"
        >
          <Text style={styles.backText}>← Voltar</Text>
        </TouchableOpacity>
        <Text style={styles.title} accessibilityRole="header" aria-level={2}>
          Configurações de IA
        </Text>
      </View>

      <Text style={styles.subtitle}>
        Configure as credenciais e modelos que o **Hermes Agent** usará para orquestrar a auditoria de acessibilidade de forma dinâmica.
      </Text>

      {/* Status Card */}
      <View style={styles.statusCard}>
        <Text style={styles.statusTitle}>Status de IA Ativo</Text>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Provider Atual:</Text>
          <Text style={styles.statusValue}>{provider.toUpperCase()}</Text>
        </View>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Modelo Principal:</Text>
          <Text style={styles.statusValue}>{model === "alto" ? "Alto (automático)" : (model || "Não especificado")}</Text>
        </View>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Chave LLM:</Text>
          <Text style={[styles.statusValue, { color: hasApiKey ? colors.success.text : colors.warning.text }]}>
            {hasApiKey ? "Configurada" : "Não Configurada"}
          </Text>
        </View>
      </View>

      {/* Form */}
      <View style={styles.form}>
        {/* Provider Radio Group */}
        <Text nativeID="providerLabel" style={styles.label}>Provedor de LLM</Text>
        <View 
          style={styles.radioGroup} 
          accessibilityRole="radiogroup" 
          accessibilityLabelledBy="providerLabel"
          aria-labelledby="providerLabel"
        >
          {PROVIDERS.map((p) => {
            const isActive = provider === p.id;
            
            if (Platform.OS === "web") {
              const elementStyle = StyleSheet.flatten([
                styles.radioButton,
                isActive && styles.radioButtonActive,
                { cursor: "pointer", userSelect: "none" }
              ]);
              const textStyle = StyleSheet.flatten([
                styles.radioText,
                isActive && styles.radioTextActive,
              ]);
              return (
                <div
                  key={p.id}
                  ref={providerRefs[p.id as keyof typeof providerRefs]}
                  onClick={() => handleSelectProvider(p.id)}
                  onKeyDown={(e) => handleKeyDown(e, p.id)}
                  role="radio"
                  aria-checked={isActive}
                  tabIndex={isActive ? 0 : -1}
                  aria-label={p.label}
                  style={elementStyle as any}
                >
                  <span style={textStyle as any}>
                    {p.label}
                  </span>
                </div>
              );
            }

            return (
              <TouchableOpacity
                key={p.id}
                ref={providerRefs[p.id as keyof typeof providerRefs]}
                style={[styles.radioButton, isActive && styles.radioButtonActive]}
                onPress={() => handleSelectProvider(p.id)}
                accessibilityRole="radio"
                accessibilityLabel={p.label}
                accessibilityHint={`Seleciona o provedor ${p.label}`}
                accessibilityState={{ checked: isActive }}
              >
                <Text style={[styles.radioText, isActive && styles.radioTextActive]}>
                  {p.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* API Key */}
        <Text nativeID="apiKeyLabel" style={styles.label}>Chave de API (API Key)</Text>
        <View style={styles.inputWithToggle}>
          <TextInput
            style={[styles.input, styles.apiKeyInput]}
            value={apiKey}
            onChangeText={setApiKey}
            placeholder="Insira a API Key do provedor selecionado…"
            secureTextEntry={!showApiKey}
            accessibilityLabelledBy="apiKeyLabel"
            aria-labelledby="apiKeyLabel"
            accessibilityHint="Digite a chave de autenticação para o provedor de IA"
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            autoComplete="off"
            placeholderTextColor={colors.text.tertiary}
            aria-invalid={errorMsg ? true : undefined}
            aria-describedby={errorMsg ? "settingsErrorMsg" : undefined}
          />
          <TouchableOpacity
            style={styles.toggleBtn}
            onPress={() => setShowApiKey(!showApiKey)}
            accessibilityRole="button"
            accessibilityLabel={showApiKey ? "Ocultar chave" : "Mostrar chave"}
            accessibilityHint="Exibe ou oculta os caracteres digitados na chave de API"
          >
            <Text style={styles.toggleBtnText}>{showApiKey ? "[Ocultar]" : "[Mostrar]"}</Text>
          </TouchableOpacity>
        </View>

        {/* Model ID Selection */}
        <Text nativeID="modelLabel" style={styles.label}>Modelo de IA (Model ID)</Text>
        
        {Platform.OS === "web" ? (
          <select
            value={selectedModelOption}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedModelOption(val);
              if (val !== "custom") {
                setModel(val);
              }
            }}
            style={StyleSheet.flatten([
              styles.input,
              {
                cursor: "pointer",
                backgroundColor: colors.bg.surface,
                color: colors.text.primary,
                borderWidth: 1,
                borderColor: colors.border.strong,
                borderRadius: radius.md,
                padding: space[3],
                fontSize: font.size.md,
                minHeight: a11y.minTarget,
                width: "100%",
                marginBottom: space[2],
                appearance: "none",
                backgroundImage: `url("data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2394A3B8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
                backgroundRepeat: "no-repeat",
                backgroundPosition: "right 12px center",
                backgroundSize: "16px",
                paddingRight: "40px"
              }
            ]) as any}
            aria-labelledby="modelLabel"
          >
            <option value="alto" style={{ backgroundColor: colors.bg.surface, color: colors.text.primary }}>
              Alto — melhor modelo para cada tarefa (recomendado)
            </option>
            {(providerModels[provider] || []).map((m) => (
              <option key={m} value={m} style={{ backgroundColor: colors.bg.surface, color: colors.text.primary }}>
                {m}{provider === "ollama-cloud" && modelCapabilities[provider]?.[m]
                  ? ` — ${[
                      modelCapabilities[provider][m].thinking ? "thinking" : "",
                      modelCapabilities[provider][m].vision ? "vision" : "",
                      modelCapabilities[provider][m].structured_outputs ? "JSON nativo" : "JSON via Luna",
                    ].filter(Boolean).join(", ")}`
                  : ""}
              </option>
            ))}
            <option value="custom" style={{ backgroundColor: colors.bg.surface, color: colors.text.primary }}>
              Outro Modelo (Digitar ID manualmente…)
            </option>
          </select>
        ) : (
          <View style={{ marginBottom: space[2] }}>
            {(selectedModelOption === "alto" || (providerModels[provider] || []).includes(selectedModelOption)) ? (
              <TouchableOpacity
                style={[styles.input, { justifyContent: "center" }]}
                onPress={() => setSelectedModelOption("custom")}
                accessibilityRole="button"
                accessibilityLabel={
                  selectedModelOption === "alto"
                    ? "Modelo atual: Alto, melhor modelo para cada tarefa. Toque para digitar um modelo customizado."
                    : `Modelo atual: ${selectedModelOption}. Toque para digitar um modelo customizado.`
                }
              >
                <Text style={{ color: colors.text.primary }}>
                  {selectedModelOption === "alto"
                    ? "Alto — melhor modelo para cada tarefa (Toque para customizar)"
                    : `${selectedModelOption} (Toque para customizar)`}
                </Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={[styles.input, { justifyContent: "center" }]}
                onPress={() => {
                  // Restaura o padrão "Alto".
                  setSelectedModelOption("alto");
                  setModel("alto");
                }}
                accessibilityRole="button"
                accessibilityLabel="Modelo customizado selecionado. Toque para voltar ao Alto (padrão)."
              >
                <Text style={{ color: colors.text.primary }}>Modelo Customizado (Toque para voltar ao Alto)</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {selectedModelOption === "custom" && (
          <TextInput
            style={[styles.input, { marginTop: space[1] }]}
            value={model}
            onChangeText={setModel}
            placeholder="Digite o identificador do modelo (Ex: gpt-4o-mini)"
            accessibilityLabelledBy="modelLabel"
            aria-labelledby="modelLabel"
            accessibilityHint="Digite o identificador do modelo de linguagem customizado"
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            autoComplete="off"
            placeholderTextColor={colors.text.tertiary}
            aria-invalid={errorMsg ? true : undefined}
            aria-describedby={errorMsg ? "settingsErrorMsg" : undefined}
          />
        )}

        {selectedModelOption === "alto" && (
          <Text style={[styles.statusHint, { marginBottom: space[3] }]} accessibilityRole="text">
            Com o Alto, você só escolhe o provedor e a chave de API: o sistema usa o
            melhor modelo recente e com suporte a ferramentas desse provedor para cada
            tarefa. Prefere fixar um modelo? Escolha-o na lista acima.
          </Text>
        )}
        {provider === "ollama-cloud" && selectedModelOption !== "alto" && selectedModelOption !== "custom" && modelCapabilities[provider]?.[selectedModelOption] && (
          <Text style={[styles.statusHint, { marginBottom: space[3] }]} accessibilityRole="text">
            Capacidades nativas: {["thinking", "vision", "tools"].filter((key) => modelCapabilities[provider][selectedModelOption][key]).join(", ") || "texto"}.
            Structured Output: o Ollama Cloud não oferece JSON Schema nativo; essa etapa será encaminhada ao GPT‑5.6 Luna pelo OpenCode Go quando configurado.
          </Text>
        )}

        {/* Base URL */}
        <Text nativeID="urlLabel" style={styles.label}>URL Base do Endpoint (Base URL — Opcional)</Text>
        <TextInput
          style={styles.input}
          value={baseUrl}
          onChangeText={setBaseUrl}
          placeholder={PROVIDERS.find(p => p.id === provider)?.placeholderUrl || "https://…"}
          accessibilityLabelledBy="urlLabel"
          aria-labelledby="urlLabel"
          accessibilityHint="Digite o endereço base da API se não estiver usando o endpoint nativo"
          autoCapitalize="none"
          autoCorrect={false}
          spellCheck={false}
          autoComplete="off"
          keyboardType="url"
          textContentType="URL"
          placeholderTextColor={colors.text.tertiary}
          aria-invalid={errorMsg ? true : undefined}
          aria-describedby={errorMsg ? "settingsErrorMsg" : undefined}
        />

        {/* Override de LLM do Chat Agêntico */}
        <View style={styles.sectionDivider} />
        <TouchableOpacity
          onPress={() => setChatLlmEnabled(!chatLlmEnabled)}
          accessibilityRole="switch"
          accessibilityState={{ checked: chatLlmEnabled }}
          accessibilityLabel="Usar um LLM diferente para o chat agêntico"
          accessibilityHint="Quando ativado, permite configurar provedor, chave, modelo e URL base próprios para o chat, diferentes dos usados na auditoria"
          style={styles.sectionToggle}
        >
          <Text style={styles.sectionToggleText}>
            {chatLlmEnabled ? "☑" : "☐"} Usar um LLM diferente para o Chat
          </Text>
        </TouchableOpacity>

        {chatLlmEnabled && (
          <View style={styles.subForm}>
            <Text nativeID="chatProviderLabel" style={styles.label}>Provedor do Chat</Text>
            {Platform.OS === "web" ? (
              <select
                value={chatLlmProvider || provider}
                onChange={(e) => setChatLlmProvider(e.target.value)}
                style={StyleSheet.flatten([styles.input, { cursor: "pointer" }]) as any}
                aria-labelledby="chatProviderLabel"
              >
                {PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            ) : (
              <TextInput
                style={styles.input}
                value={chatLlmProvider}
                onChangeText={setChatLlmProvider}
                placeholder={provider}
                accessibilityLabelledBy="chatProviderLabel"
                autoCapitalize="none"
                autoCorrect={false}
                spellCheck={false}
                autoComplete="off"
                placeholderTextColor={colors.text.tertiary}
              />
            )}

            <Text nativeID="chatKeyLabel" style={styles.label}>Chave de API do Chat</Text>
            <TextInput
              style={styles.input}
              value={chatLlmApiKey}
              onChangeText={setChatLlmApiKey}
              placeholder="Deixe vazio para usar a chave principal"
              secureTextEntry
              accessibilityLabelledBy="chatKeyLabel"
              autoCapitalize="none"
              autoCorrect={false}
              spellCheck={false}
              autoComplete="off"
              placeholderTextColor={colors.text.tertiary}
            />
            <Text style={styles.statusHint}>
              {hasChatLlmApiKey ? "Chave própria do chat configurada." : "Usando a chave principal do provedor acima."}
            </Text>

            <Text nativeID="chatModelLabel" style={styles.label}>Modelo do Chat</Text>
            <TextInput
              style={styles.input}
              value={chatLlmModel}
              onChangeText={setChatLlmModel}
              placeholder="Ex: gpt-5, claude-opus-5 (vazio = Alto)"
              accessibilityLabelledBy="chatModelLabel"
              autoCapitalize="none"
              autoCorrect={false}
              spellCheck={false}
              autoComplete="off"
              placeholderTextColor={colors.text.tertiary}
            />

            <Text nativeID="chatUrlLabel" style={styles.label}>URL Base do Chat (Opcional)</Text>
            <TextInput
              style={styles.input}
              value={chatLlmBaseUrl}
              onChangeText={setChatLlmBaseUrl}
              placeholder="https://…"
              accessibilityLabelledBy="chatUrlLabel"
              autoCapitalize="none"
              autoCorrect={false}
              spellCheck={false}
              autoComplete="off"
              keyboardType="url"
              textContentType="URL"
              placeholderTextColor={colors.text.tertiary}
            />
          </View>
        )}

        {/* Chaves de Serviços de Terceiros */}
        <View style={styles.sectionDivider} />
        <Text style={styles.label} accessibilityRole="header" aria-level={3}>
          Chaves de Serviços de Terceiros
        </Text>
        <Text style={styles.statusHint}>
          Cada chave é salva imediatamente ao clicar em "Salvar" e não é reexibida depois, por segurança.
        </Text>
        {THIRD_PARTY_SERVICES.map((svc) => (
          <View key={svc.id} style={styles.serviceKeyRow}>
            <Text nativeID={`svc-${svc.id}-label`} style={styles.label}>{svc.label}</Text>
            <View style={styles.inputWithToggle}>
              <TextInput
                style={[styles.input, styles.serviceKeyInput]}
                value={serviceKeyValues[svc.id] || ""}
                onChangeText={(v) => setServiceKeyValues((s) => ({ ...s, [svc.id]: v }))}
                placeholder={svc.placeholder}
                secureTextEntry
                accessibilityLabelledBy={`svc-${svc.id}-label`}
                autoCapitalize="none"
                autoCorrect={false}
                spellCheck={false}
                autoComplete="off"
                placeholderTextColor={colors.text.tertiary}
              />
              <TouchableOpacity
                style={styles.serviceKeySaveBtn}
                onPress={() => handleSaveServiceKey(svc.id)}
                disabled={serviceKeySaving === svc.id || !(serviceKeyValues[svc.id] || "").trim()}
                accessibilityRole="button"
                accessibilityLabel={`Salvar chave de ${svc.label}`}
              >
                {serviceKeySaving === svc.id ? (
                  <ActivityIndicator size="small" color={colors.accent.text} />
                ) : (
                  <Text style={styles.serviceKeySaveBtnText}>Salvar</Text>
                )}
              </TouchableOpacity>
            </View>
            {!!serviceKeyStatus[svc.id] && (
              <Text
                style={styles.statusHint}
                accessibilityRole={"status" as any}
                role="status"
                accessibilityLiveRegion="polite"
              >
                {serviceKeyStatus[svc.id]}
              </Text>
            )}
          </View>
        ))}

        {/* Feedback alerts */}
        {statusMsg && (
          <Text 
            nativeID="settingsSuccessMsg"
            style={styles.successMsg} 
            accessibilityRole={"status" as any}
            role="status" 
            accessibilityLiveRegion="polite"
          >
            {statusMsg}
          </Text>
        )}
        {errorMsg && (
          <Text 
            nativeID="settingsErrorMsg"
            style={styles.errorMsg} 
            accessibilityRole="alert"
            role="alert" 
            accessibilityLiveRegion="assertive"
          >
            {errorMsg}
          </Text>
        )}

        {/* Actions */}
        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
          onPress={handleSave}
          disabled={saving}
          accessibilityRole="button"
          accessibilityState={{ disabled: saving }}
          accessibilityLabel={saving ? "Salvando Configurações de IA, aguarde" : "Salvar Configurações de IA"}
          accessibilityHint={saving ? "Salvando configurações no servidor, por favor aguarde" : "Salva as configurações de provedor e modelo de IA"}
        >
          {saving ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Text style={styles.saveBtnText}>Salvar Configuração</Text>
          )}
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg.root },
  contentContainer: { padding: space[6], maxWidth: 680, alignSelf: "center", width: "100%" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: colors.bg.root },
  loadingText: { marginTop: space[4], color: colors.text.secondary, fontSize: font.size.base },
  topBar: { flexDirection: "row", alignItems: "center", paddingBottom: space[4], borderBottomWidth: 1, borderBottomColor: colors.border.DEFAULT, gap: space[4], marginBottom: space[4] },
  backBtn: { paddingVertical: space[1], minHeight: 44, justifyContent: "center" },
  backText: { fontSize: font.size.base, color: colors.accent.text, fontWeight: font.weight.semibold },
  title: { fontSize: font.size.xl, fontWeight: font.weight.extrabold, color: colors.text.primary, fontFamily: displayFont },
  subtitle: { fontSize: font.size.base, color: colors.text.secondary, marginBottom: space[5], lineHeight: 22 },
  statusCard: { backgroundColor: colors.bg.surface, borderLeftWidth: 4, borderLeftColor: colors.accent.DEFAULT, borderRadius: radius.md, padding: space[4], marginBottom: space[6], borderWidth: 1, borderColor: colors.border.DEFAULT, ...shadow.sm },
  statusTitle: { fontSize: font.size.base, fontWeight: font.weight.bold, color: colors.text.primary, marginBottom: space[3], fontFamily: displayFont },
  statusRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: space[2] },
  statusLabel: { fontSize: font.size.sm, color: colors.text.secondary, fontWeight: font.weight.semibold },
  statusValue: { fontSize: font.size.sm, color: colors.text.primary, fontFamily: monoFont },
  statusHint: { fontSize: font.size.xs, color: colors.text.tertiary, marginTop: space[2], fontStyle: "italic" },
  form: { gap: space[4] },
  label: { fontSize: font.size.sm, fontWeight: font.weight.bold, color: colors.text.secondary, marginBottom: space[1] },
  input: { borderWidth: 1, borderColor: colors.border.strong, borderRadius: radius.md, padding: space[3], fontSize: font.size.md, minHeight: a11y.minTarget, backgroundColor: colors.bg.surface, color: colors.text.primary, width: "100%" },
  inputWithToggle: { flexDirection: "row", alignItems: "center", position: "relative", width: "100%" },
  apiKeyInput: { paddingRight: 50 },
  toggleBtn: { position: "absolute", right: 12, height: 44, justifyContent: "center", alignItems: "center", width: a11y.minTarget },
  toggleBtnText: { fontSize: 16 },
  radioGroup: { flexDirection: "row", flexWrap: "wrap", gap: space[2], marginBottom: space[2] },
  radioButton: { borderWidth: 1, borderColor: colors.border.strong, borderRadius: radius.sm, paddingHorizontal: space[3], paddingVertical: space[2], backgroundColor: colors.bg.surface, minHeight: a11y.minTarget, justifyContent: "center" },
  radioButtonActive: { borderColor: colors.accent.DEFAULT, backgroundColor: colors.accent.subtle },
  radioText: { fontSize: font.size.sm, color: colors.text.secondary, fontWeight: font.weight.medium },
  radioTextActive: { color: colors.accent.text, fontWeight: font.weight.bold },
  saveBtn: { backgroundColor: colors.accent.DEFAULT, borderRadius: radius.md, padding: space[4], alignItems: "center", minHeight: a11y.minTarget, justifyContent: "center", marginTop: space[4], ...shadow.glow },
  saveBtnDisabled: { opacity: 0.5, shadowOpacity: 0 },
  saveBtnText: { color: "#fff", fontWeight: font.weight.bold, fontSize: font.size.md, fontFamily: displayFont },
  sectionDivider: { borderTopWidth: 1, borderTopColor: colors.border.DEFAULT, marginTop: space[3], paddingTop: space[3] },
  sectionToggle: { minHeight: a11y.minTarget, justifyContent: "center", marginBottom: space[2] },
  sectionToggleText: { fontSize: font.size.base, fontWeight: font.weight.bold, color: colors.text.primary },
  subForm: { gap: space[2], marginBottom: space[2] },
  serviceKeyRow: { marginBottom: space[3] },
  serviceKeyInput: { paddingRight: 90 },
  serviceKeySaveBtn: { position: "absolute", right: 6, height: a11y.minTarget, minWidth: a11y.minTarget, paddingHorizontal: space[3], justifyContent: "center", alignItems: "center", backgroundColor: colors.accent.DEFAULT, borderRadius: radius.sm },
  serviceKeySaveBtnText: { color: "#fff", fontSize: font.size.sm, fontWeight: font.weight.bold },
  successMsg: { color: colors.success.text, fontSize: font.size.sm, backgroundColor: colors.success.bg, padding: space[3], borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success.border },
  errorMsg: { color: colors.danger.text, fontSize: font.size.sm, backgroundColor: colors.danger.bg, padding: space[3], borderRadius: radius.sm, borderWidth: 1, borderColor: colors.danger.border },
});
