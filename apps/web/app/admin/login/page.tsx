"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthForm } from "@/components/admin/auth-form";
import { adminApi, errorMessage, setToken } from "@/components/admin/client";

export default function LoginPage() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function login({ email, password }: { email: string; password: string }) {
    setPending(true);
    setError(null);
    try {
      const { token } = await adminApi.login({ email, password });
      setToken(token);
      router.replace("/admin/positions");
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  }

  return <AuthForm mode="login" pending={pending} error={error} onSubmit={login} />;
}
