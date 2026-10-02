const makeWebpackConfig = require("../../../web/webpack.config.js");
const webpack = require("../../../web/node_modules/webpack");
const fs = require("fs");
const path = require("path");

test("configura a URL da API no DefinePlugin fornecido pelo Expo", async () => {
  const config = await makeWebpackConfig(
    { mode: "development", platform: "web" },
    { mode: "development" },
  );
  const definePlugins = config.plugins.filter(
    (plugin: { constructor: { name: string } }) => plugin.constructor.name === "DefinePlugin",
  );

  expect(definePlugins).toHaveLength(1);
  expect(definePlugins[0].constructor).toBe(webpack.DefinePlugin);
  expect(definePlugins[0].definitions).toMatchObject({
    "process.env.EXPO_PUBLIC_API_URL": JSON.stringify("http://localhost:8001"),
    "process.env.EXPO_PUBLIC_QA_API_TOKEN": JSON.stringify(""),
  });
});

test("o ponto de entrada do Expo fica dentro do projeto", () => {
  const projectRoot = path.resolve(__dirname, "../../../web");
  const entry = require("../../../web/package.json").main;
  expect(entry).toBe("index.js");
  expect(fs.existsSync(path.join(projectRoot, entry))).toBe(true);
});
