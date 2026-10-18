import React, { useCallback, useEffect, useRef, useState } from "react";
import { Platform, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { a11y, colors, font, radius } from "../design/tokens";
import {
  deleteMcpServer,
  deleteSkill,
  getSkill,
  listMcpServers,
  listSkills,
  saveSkill,
  type McpServerSummary,
  type SkillSummary,
} from "../services/memory";

/**
 * Memória de longo prazo e servidores MCP registrados, à vista da pessoa (regras 10 e 18): ver, editar e apagar.
 * Nada aqui é configuração obrigatória; é transparência sobre o que o assistente aprendeu e o que está conectado.
 *
 * Acessibilidade: listas de verdade (ul/li) na web, nome de botão com o nome do item, apagar em dois passos, edição
 * com foco no primeiro campo, e uma região de status que já existe vazia no DOM antes de receber texto.
 */

const ORIGEM: Record<string, string> = {
  pessoa: "escrita ou editada por você",
  assistente: "aprendida pelo assistente",
  "conteudo-nao-confiavel": "veio de conteúdo não confiável (só dado, nunca instrução)",
};

function origemTexto(origem: string): string {
  return ORIGEM[origem] ?? origem;
}

type Editing = { name: string; description: string; instructions: string } | null;

export function MemoryPanel() {
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [servers, setServers] = useState<McpServerSummary[] | null>(null);
  const [status, setStatus] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const firstFieldRef = useRef<TextInput | null>(null);
  const headingRef = useRef<Text | null>(null);

  const load = useCallback(async () => {
    setSkills(await listSkills());
    setServers(await listMcpServers());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (editing) firstFieldRef.current?.focus();
  }, [editing]);

  async function startEdit(name: string) {
    const detail = await getSkill(name);
    if (!detail) {
      setStatus(`Não foi possível abrir a habilidade ${name}.`);
      return;
    }
    setEditing({ name, description: detail.description, instructions: detail.body });
  }

  async function saveEdit() {
    if (!editing) return;
    const ok = await saveSkill(editing.name, editing.description, editing.instructions);
    setStatus(ok ? `Habilidade ${editing.name} salva.` : `Não foi possível salvar a habilidade ${editing.name}. Confira se o texto não tem chave ou senha.`);
    if (ok) {
      setEditing(null);
      await load();
    }
  }

  async function removeSkill(name: string) {
    const ok = await deleteSkill(name);
    setConfirming(null);
    setStatus(ok ? `Habilidade ${name} apagada.` : `Não foi possível apagar a habilidade ${name}.`);
    await load();
    headingRef.current?.focus?.();
  }

  async function removeServer(name: string) {
    const ok = await deleteMcpServer(name);
    setStatus(ok ? `Servidor ${name} removido.` : `Não foi possível remover o servidor ${name}.`);
    await load();
    headingRef.current?.focus?.();
  }

  const list = (items: React.ReactNode[], label: string) =>
    Platform.OS === "web"
      ? React.createElement("ul", { "aria-label": label, style: { listStyle: "none", margin: 0, padding: 0 } }, items)
      : <View>{items}</View>;
  const item = (key: string, children: React.ReactNode) =>
    Platform.OS === "web"
      ? React.createElement("li", { key, style: { margin: 0, padding: 0 } }, children)
      : <View key={key}>{children}</View>;

  return (
    <View style={styles.root}>
      <Text ref={headingRef} accessibilityRole="header" aria-level={2} style={styles.title} {...({ tabIndex: -1 } as object)}>
        Memória e conexões
      </Text>
      <Text style={styles.hint}>
        O que o assistente aprendeu fica aqui, à sua vista. Você pode corrigir ou apagar. Nada disso precisa ser configurado.
      </Text>

      {/* A região de status existe sempre, vazia, antes de receber texto */}
      <View accessibilityLiveRegion="polite" {...({ role: "status" } as object)} style={styles.status}>
        <Text style={styles.statusText}>{status}</Text>
      </View>

      <Text accessibilityRole="header" aria-level={3} style={styles.subtitle}>Habilidades aprendidas</Text>
      {skills === null && <Text style={styles.meta}>Memória indisponível agora. O assistente precisa estar rodando.</Text>}
      {skills !== null && skills.length === 0 && <Text style={styles.meta}>Nada aprendido ainda.</Text>}
      {skills !== null && skills.length > 0 &&
        list(
          skills.map((s) =>
            item(
              s.name,
              <View style={styles.row}>
                <Text style={styles.name}>{s.name}</Text>
                <Text style={styles.meta}>{s.description}</Text>
                <Text style={styles.meta}>{`Origem: ${origemTexto(s.origem)}. Confiança: ${s.confianca}.`}</Text>
                {editing?.name === s.name ? (
                  <View>
                    <TextInput
                      ref={firstFieldRef}
                      value={editing.description}
                      onChangeText={(text) => setEditing({ ...editing, description: text })}
                      accessibilityLabel={`Descrição da habilidade ${s.name}`}
                      style={styles.input}
                    />
                    <TextInput
                      value={editing.instructions}
                      onChangeText={(text) => setEditing({ ...editing, instructions: text })}
                      accessibilityLabel={`Instruções da habilidade ${s.name}`}
                      multiline
                      style={[styles.input, styles.multiline]}
                    />
                    <View style={styles.actions}>
                      <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Salvar a habilidade ${s.name}`} onPress={() => void saveEdit()} style={styles.primary}>
                        <Text style={styles.primaryText}>Salvar</Text>
                      </TouchableOpacity>
                      <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Cancelar a edição de ${s.name}`} onPress={() => setEditing(null)} style={styles.secondary}>
                        <Text style={styles.secondaryText}>Cancelar</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : confirming === s.name ? (
                  <View style={styles.actions}>
                    <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Confirmar: apagar a habilidade ${s.name}`} onPress={() => void removeSkill(s.name)} style={styles.danger}>
                      <Text style={styles.primaryText}>Confirmar apagar</Text>
                    </TouchableOpacity>
                    <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Cancelar: não apagar ${s.name}`} onPress={() => setConfirming(null)} style={styles.secondary}>
                      <Text style={styles.secondaryText}>Cancelar</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <View style={styles.actions}>
                    <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Editar a habilidade ${s.name}`} onPress={() => void startEdit(s.name)} style={styles.secondary}>
                      <Text style={styles.secondaryText}>Editar</Text>
                    </TouchableOpacity>
                    <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Apagar a habilidade ${s.name}`} onPress={() => setConfirming(s.name)} style={styles.secondary}>
                      <Text style={styles.secondaryText}>Apagar</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>,
            ),
          ),
          "Habilidades aprendidas",
        )}

      <Text accessibilityRole="header" aria-level={3} style={styles.subtitle}>Servidores MCP conectados</Text>
      {servers === null && <Text style={styles.meta}>Lista indisponível agora.</Text>}
      {servers !== null && servers.length === 0 && <Text style={styles.meta}>Nenhum servidor externo conectado.</Text>}
      {servers !== null && servers.length > 0 &&
        list(
          servers.map((srv) =>
            item(
              srv.name,
              <View style={styles.row}>
                <Text style={styles.name}>{srv.name}</Text>
                <Text style={styles.meta}>{`Comando: ${srv.command} ${srv.args.join(" ")}`.trim()}</Text>
                <Text style={styles.meta}>
                  {srv.env_names.length ? `Recebe só estas credenciais: ${srv.env_names.join(", ")}.` : "Não recebe nenhuma credencial."}
                </Text>
                <View style={styles.actions}>
                  <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Remover o servidor ${srv.name}`} onPress={() => void removeServer(srv.name)} style={styles.secondary}>
                    <Text style={styles.secondaryText}>Remover</Text>
                  </TouchableOpacity>
                </View>
              </View>,
            ),
          ),
          "Servidores MCP conectados",
        )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { marginTop: 24, paddingTop: 16, borderTopWidth: 1, borderTopColor: colors.border.DEFAULT },
  title: { color: colors.text.primary, fontFamily: font.display, fontSize: 18, fontWeight: "700", marginBottom: 4 },
  subtitle: { color: colors.text.primary, fontFamily: font.body, fontSize: 15, fontWeight: "600", marginTop: 16, marginBottom: 6 },
  hint: { color: colors.text.secondary, fontFamily: font.body, fontSize: 13, marginBottom: 8 },
  status: { minHeight: 0 },
  statusText: { color: colors.text.secondary, fontFamily: font.body, fontSize: 13 },
  row: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border.DEFAULT },
  name: { color: colors.text.primary, fontFamily: font.body, fontSize: 14, fontWeight: "600" },
  meta: { color: colors.text.secondary, fontFamily: font.body, fontSize: 13, marginTop: 2 },
  actions: { flexDirection: "row", gap: 8, marginTop: 8 },
  input: {
    minHeight: a11y.minTarget,
    borderWidth: 1,
    borderColor: colors.border.strong,
    borderRadius: radius.md,
    paddingHorizontal: 10,
    color: colors.text.primary,
    backgroundColor: colors.bg.surface,
    fontFamily: font.body,
    fontSize: 14,
    marginTop: 8,
  },
  multiline: { minHeight: 120, textAlignVertical: "top", paddingTop: 8 },
  primary: { minHeight: a11y.minTarget, justifyContent: "center", paddingHorizontal: 14, borderRadius: radius.md, backgroundColor: colors.accent.DEFAULT },
  danger: { minHeight: a11y.minTarget, justifyContent: "center", paddingHorizontal: 14, borderRadius: radius.md, backgroundColor: colors.danger.DEFAULT },
  primaryText: { color: colors.text.onAccent, fontFamily: font.body, fontSize: 14, fontWeight: "600" },
  secondary: { minHeight: a11y.minTarget, justifyContent: "center", paddingHorizontal: 14, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border.strong },
  secondaryText: { color: colors.accent.text, fontFamily: font.body, fontSize: 14 },
});
