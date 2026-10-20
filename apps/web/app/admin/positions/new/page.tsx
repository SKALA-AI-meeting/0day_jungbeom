"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { adminApi, errorMessage, useLoad, useToken } from "@/components/admin/client";
import { PositionForm } from "@/components/admin/position-form";

export default function NewPositionPage() {
  const router = useRouter();
  const token = useToken();
  const { data: catalog, error: loadError } = useLoad(adminApi.catalog);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(value: { name: string; elements: string[] }) {
    if (!token) return;
    setPending(true);
    setError(null);
    try {
      const created = await adminApi.createPosition(token, value);
      router.replace(`/admin/positions/${created.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setPending(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-semibold">채용 건 만들기</h1>
      {(loadError || error) && (
        <p role="alert" className="text-danger">
          {loadError ?? error}
        </p>
      )}
      {catalog && <PositionForm catalog={catalog} pending={pending} onSubmit={create} />}
    </>
  );
}
