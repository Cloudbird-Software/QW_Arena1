import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/", "coverage/", "reports/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // ESM 路径下保留未用参数（对齐 E2E 签名：模板参数前瞻保留，不参与实现）
    files: ["**/*.ts"],
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    files: ["**/*.cjs"],
    languageOptions: { sourceType: "script", globals: { module: "writable" } },
  },
  {
    // 仓内 Node 工具脚本（tools/*.mjs）：node 24 全局面
    files: ["**/*.mjs"],
    languageOptions: {
      globals: {
        process: "readonly",
        console: "readonly",
        Buffer: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        URL: "readonly",
        fetch: "readonly",
        Response: "readonly",
        AbortController: "readonly",
        globalThis: "readonly",
      },
    },
  },
);
