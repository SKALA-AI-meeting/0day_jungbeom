import { cn } from "./cn";

export type AvatarTone = "manager" | "colleague" | "candidate" | "system";

const TONE: Record<AvatarTone, string> = {
  manager: "bg-person-manager",
  colleague: "bg-person-colleague",
  candidate: "bg-person-candidate",
  system: "bg-person-system",
};

const SIZE = { 20: "size-5 text-[10px]", 28: "size-7 text-xs", 36: "size-9 text-sm" } as const;

/** 이름의 첫 글자(문자 단위). 별칭이 비어 있으면 "?" */
export function initial(name: string) {
  const first = name.trim();
  if (!first) return "?";
  const Segmenter = (Intl as { Segmenter?: typeof Intl.Segmenter }).Segmenter;
  if (Segmenter) {
    const [segment] = new Segmenter("ko", { granularity: "grapheme" }).segment(first);
    return segment?.segment ?? "?";
  }
  return first[0];
}

export type AvatarProps = {
  /** 이니셜로 쓸 글자(보통 이름의 첫 글자) */
  label: string;
  tone: AvatarTone;
  size?: 20 | 28 | 36;
  online?: boolean;
  /** 화면 낭독용 이름 */
  name?: string;
  className?: string;
};

export function Avatar({ label, tone, size = 28, online, name, className }: AvatarProps) {
  return (
    <span
      role="img"
      aria-label={name ?? label}
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white select-none",
        TONE[tone],
        SIZE[size],
        className,
      )}
    >
      {label}
      {online && (
        <span className="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-surface bg-success" />
      )}
    </span>
  );
}

export type AvatarGroupProps = {
  people: Omit<AvatarProps, "size">[];
  size?: 20 | 28;
  className?: string;
};

/** 채널 멤버 묶음. 겹침 -6px(design-system.md) */
export function AvatarGroup({ people, size = 20, className }: AvatarGroupProps) {
  return (
    <span className={cn("inline-flex items-center", className)}>
      {people.map((person, i) => (
        <Avatar
          key={`${person.tone}-${i}`}
          {...person}
          size={size}
          className={cn("ring-2 ring-surface", i > 0 && "-ml-1.5")}
        />
      ))}
    </span>
  );
}
