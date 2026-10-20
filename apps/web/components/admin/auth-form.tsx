"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, Card, Input } from "@/components/ui";

export type AuthValues = { email: string; password: string; company_name: string };

export type AuthFormProps = {
  mode: "login" | "signup";
  pending?: boolean;
  /** 서버가 돌려준 오류 문구 */
  error?: string | null;
  onSubmit: (values: AuthValues) => void;
};

export function AuthForm({ mode, pending, error, onSubmit }: AuthFormProps) {
  const [values, setValues] = useState<AuthValues>({ email: "", password: "", company_name: "" });
  const signup = mode === "signup";
  const set = (key: keyof AuthValues) => (event: { target: { value: string } }) =>
    setValues((prev) => ({ ...prev, [key]: event.target.value }));

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(values);
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 px-6 py-20">
      <h1 className="text-2xl font-semibold">{signup ? "관리자 가입" : "관리자 로그인"}</h1>
      <Card>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          {signup && (
            <Input
              label="회사 이름"
              value={values.company_name}
              onChange={set("company_name")}
              required
            />
          )}
          <Input
            label="이메일"
            type="email"
            autoComplete="email"
            value={values.email}
            onChange={set("email")}
            required
          />
          <Input
            label="비밀번호"
            type="password"
            autoComplete={signup ? "new-password" : "current-password"}
            value={values.password}
            onChange={set("password")}
            required
          />
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <Button type="submit" loading={pending}>
            {signup ? "가입하고 시작" : "로그인"}
          </Button>
        </form>
      </Card>
      <p className="text-sm text-muted">
        {signup ? "이미 계정이 있나요? " : "계정이 없나요? "}
        <Link
          className="text-accent underline-offset-4 hover:underline"
          href={signup ? "/admin/login" : "/admin/signup"}
        >
          {signup ? "로그인" : "가입"}
        </Link>
      </p>
    </main>
  );
}
