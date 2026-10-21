import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { useId } from "react";

import { cn } from "./cn";

const control =
  "w-full rounded-md border border-line bg-surface px-3 py-2 text-base text-ink transition-[border-color,box-shadow] duration-150 placeholder:text-subtle read-only:bg-surface-sunken focus:border-accent focus:ring-1 focus:ring-accent focus-visible:outline-none aria-invalid:border-danger disabled:opacity-60";

type FieldChrome = {
  label?: ReactNode;
  /** 입력 아래 안내 문구 */
  hint?: ReactNode;
  /** 오류 문구. 있으면 hint 대신 보인다 */
  error?: ReactNode;
};

function Chrome({
  id,
  label,
  hint,
  error,
  children,
}: FieldChrome & { id: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-sm text-danger">{error}</p>
      ) : (
        hint && <p className="text-sm text-muted">{hint}</p>
      )}
    </div>
  );
}

export type InputProps = InputHTMLAttributes<HTMLInputElement> & FieldChrome;

export function Input({ label, hint, error, className, id, ...rest }: InputProps) {
  const fallback = useId();
  const inputId = id ?? fallback;
  return (
    <Chrome id={inputId} label={label} hint={hint} error={error}>
      <input
        id={inputId}
        aria-invalid={!!error || undefined}
        className={cn(control, className)}
        {...rest}
      />
    </Chrome>
  );
}

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & FieldChrome;

export function Textarea({ label, hint, error, className, id, ...rest }: TextareaProps) {
  const fallback = useId();
  const inputId = id ?? fallback;
  return (
    <Chrome id={inputId} label={label} hint={hint} error={error}>
      <textarea
        id={inputId}
        aria-invalid={!!error || undefined}
        className={cn(control, "min-h-24 resize-y", className)}
        {...rest}
      />
    </Chrome>
  );
}

export type SelectOption = { value: string; label: ReactNode; disabled?: boolean };

export type SelectProps = Omit<InputHTMLAttributes<HTMLSelectElement>, "children"> &
  FieldChrome & { options: SelectOption[] };

export function Select({ label, hint, error, className, id, options, ...rest }: SelectProps) {
  const fallback = useId();
  const inputId = id ?? fallback;
  return (
    <Chrome id={inputId} label={label} hint={hint} error={error}>
      <select
        id={inputId}
        aria-invalid={!!error || undefined}
        className={cn(control, className)}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </Chrome>
  );
}
