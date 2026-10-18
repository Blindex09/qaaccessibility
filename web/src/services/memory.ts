// Memória de longo prazo e servidores MCP registrados: a pessoa vê, edita e apaga (regras 10 e 18).
import { BASE_URL } from "./chat";

const API_TOKEN = process.env.EXPO_PUBLIC_QA_API_TOKEN ?? "";
const HEADERS = {
  "Content-Type": "application/json",
  ...(API_TOKEN ? { "X-QA-Accessibility-Token": API_TOKEN } : {}),
};

export interface SkillSummary {
  name: string;
  description: string;
  origem: string;
  confianca: string;
}

export interface SkillDetail {
  name: string;
  description: string;
  body: string;
  metadata: Record<string, string>;
}

export interface McpServerSummary {
  name: string;
  command: string;
  args: string[];
  env_names: string[];
  note: string;
}

async function request<T>(path: string, init?: Parameters<typeof fetch>[1]): Promise<T | null> {
  try {
    const resp = await fetch(`${BASE_URL}${path}`, { headers: HEADERS, ...init });
    if (!resp.ok) return null;
    return (await resp.json()) as T;
  } catch {
    return null;
  }
}

export async function listSkills(): Promise<SkillSummary[] | null> {
  const data = await request<{ skills: SkillSummary[] }>("/memory/skills");
  return data ? data.skills : null;
}

export async function getSkill(name: string): Promise<SkillDetail | null> {
  return request<SkillDetail>(`/memory/skills/${encodeURIComponent(name)}`);
}

export async function saveSkill(name: string, description: string, instructions: string): Promise<boolean> {
  const data = await request<{ name: string }>(`/memory/skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify({ description, instructions }),
  });
  return data !== null;
}

export async function deleteSkill(name: string): Promise<boolean> {
  return (await request<{ deleted: boolean }>(`/memory/skills/${encodeURIComponent(name)}`, { method: "DELETE" })) !== null;
}

export async function listMcpServers(): Promise<McpServerSummary[] | null> {
  const data = await request<{ servers: McpServerSummary[] }>("/memory/mcp-servers");
  return data ? data.servers : null;
}

export async function deleteMcpServer(name: string): Promise<boolean> {
  return (await request<{ deleted: boolean }>(`/memory/mcp-servers/${encodeURIComponent(name)}`, { method: "DELETE" })) !== null;
}
