// compose healthcheck(`wget http://localhost:3000/api/health`)가 보는 경로.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
