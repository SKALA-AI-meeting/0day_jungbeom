import Image from "next/image";

import { cn } from "./cn";

export type WordmarkProps = { className?: string };

/** "Day Zero" 워드마크(public/brand/wordmark.svg). 높이는 호출부 className(h-5·h-6)이 정하고 폭은 비율을 따른다 */
export function Wordmark({ className }: WordmarkProps) {
  return (
    <Image
      src="/brand/wordmark.svg"
      alt="Day Zero"
      width={150}
      height={30}
      unoptimized
      priority
      className={cn("w-auto", className)}
    />
  );
}
