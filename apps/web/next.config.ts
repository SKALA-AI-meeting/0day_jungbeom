import type { NextConfig } from "next";

// standalone: Docker 이미지에서 `node server.js`로 실행한다.
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
