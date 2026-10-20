"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthForm, type AuthValues } from "@/components/admin/auth-form";
import { adminApi, errorMessage, setToken } from "@/components/admin/client";

export default function SignupPage() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signup(values: AuthValues) {
    setPending(true);
    setError(null);
    try {
      const { token } = await adminApi.signup(values);
      setToken(token);
      router.replace("/admin/positions");
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  }

  return <AuthForm mode="signup" pending={pending} error={error} onSubmit={signup} />;
}
