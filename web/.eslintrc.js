module.exports = {
  root: true,
  extends: ["expo", "eslint:recommended"],
  // This app runs conditionally on web (Platform.OS === "web") in the same .tsx files as
  // native code, rather than splitting into *.web.tsx -- the expo config's web override
  // only applies to that split, so DOM/browser and web-timer globals are declared here
  // for the whole src/ tree.
  env: { browser: true, es2021: true },
  ignorePatterns: ["web-build/", "node_modules/"],
};
