import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier";

const config = [
  ...nextVitals,
  ...nextTypescript,
  prettier,
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
];

export default config;
