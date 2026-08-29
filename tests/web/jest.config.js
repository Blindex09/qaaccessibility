module.exports = {
  testEnvironment: "jsdom",
  testMatch: ["**/*.test.ts", "**/*.test.tsx"],
  moduleNameMapper: {
    "^../../src/(.*)$": "<rootDir>/../../web/src/$1",
  },
  collectCoverageFrom: ["../../web/src/services/**/*.ts"],
};
