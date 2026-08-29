const createExpoWebpackConfigAsync = require('@expo/webpack-config');
const webpack = require('webpack');

const API_PREFIXES = [
  '/analyze',
  '/fix',
  '/report',
  '/checklist',
  '/health',
  '/export',
  '/settings',
  '/chat',
  '/models',
  '/preview',
  '/webhook',
];

module.exports = async function (env, argv) {
  const config = await createExpoWebpackConfigAsync(env, argv);

  // Inject EXPO_PUBLIC_API_URL at build time so process.env works in the bundle
  // Use nullish coalescing (??) so empty string "" stays as relative URLs (proxied)
  const apiUrl = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8001';
  const apiToken = process.env.EXPO_PUBLIC_QA_API_TOKEN ?? '';
  config.plugins.push(
    new webpack.DefinePlugin({
      'process.env.EXPO_PUBLIC_API_URL': JSON.stringify(apiUrl),
      'process.env.EXPO_PUBLIC_QA_API_TOKEN': JSON.stringify(apiToken),
    })
  );

  // Dev server proxy: forward backend API prefixes to FastAPI.
  if (config.devServer) {
    config.devServer.proxy = Object.fromEntries(
      API_PREFIXES.map((prefix) => [prefix, { target: apiUrl, changeOrigin: true }])
    );
  }

  return config;
};
