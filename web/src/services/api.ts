import axios from "axios";

export const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  (typeof window !== "undefined"
    ? window.location.protocol + "//" + window.location.hostname + ":8001"
    : "http://localhost:8001");
const API_TOKEN = process.env.EXPO_PUBLIC_QA_API_TOKEN ?? "";

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
    ...(API_TOKEN ? { "X-QA-Accessibility-Token": API_TOKEN } : {}),
  },
});

// ─── Settings (configuração de IA) ───────────────────────────────────────────

export interface SettingsData {
  llm_provider: string;
  llm_model?: string;
  llm_base_url?: string;
  has_llm_api_key: boolean;
  llm_api_key?: string;
  // Overrides opcionais do LLM usado pelo chat agêntico (ChatScreen) -- quando
  // ausentes, o chat usa os llm_* acima (ver backend chat_llm_config).
  chat_llm_provider?: string;
  chat_llm_model?: string;
  chat_llm_base_url?: string;
  has_chat_llm_api_key?: boolean;
  chat_llm_api_key?: string;
}

export async function getSettings(): Promise<SettingsData> {
  const { data } = await api.get<SettingsData>("/settings/");
  return data;
}

export async function saveSettings(settings: Partial<SettingsData>): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>("/settings/", settings);
  return data;
}

export async function saveServiceKey(serviceName: string, apiKey: string): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>("/settings/service-key", {
    service_name: serviceName,
    api_key: apiKey,
  });
  return data;
}

