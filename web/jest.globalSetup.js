// O babel-preset-expo inlina as variáveis EXPO_PUBLIC_* no momento do transform,
// que acontece nos workers do jest -- defini-las dentro do teste é tarde demais.
// Aqui (processo principal, antes dos workers) elas chegam ao transform.
module.exports = function globalSetup() {
  process.env.EXPO_PUBLIC_API_URL = process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8001";
  process.env.EXPO_PUBLIC_QA_API_TOKEN = process.env.EXPO_PUBLIC_QA_API_TOKEN || "session-token";
};
