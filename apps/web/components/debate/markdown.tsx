// 읽기 전용 Markdown 뷰어: 회사 자료와 받은 문서를 제목·목록·표·강조가 보이게 그린다.
// 원문 HTML은 그리지 않는다(skipHtml). 표는 좁은 화면에서 표만 가로로 스크롤한다.
import type { ComponentPropsWithoutRef, ElementType } from "react";
import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { cn } from "@/components/ui";

/** 태그에 읽기용 클래스만 입힌다. react-markdown이 넘기는 node(구문 트리)는 DOM에 내리지 않는다 */
function styled<T extends ElementType>(Tag: T, base: string) {
  function Styled({ node, className, ...rest }: ComponentPropsWithoutRef<T> & ExtraProps) {
    void node;
    const Element = Tag as ElementType;
    return <Element className={cn(base, className)} {...rest} />;
  }
  return Styled;
}

const COMPONENTS: Components = {
  h1: styled("h1", "mt-6 mb-3 text-xl font-semibold first:mt-0"),
  h2: styled("h2", "mt-6 mb-2 text-lg font-semibold first:mt-0"),
  h3: styled("h3", "mt-5 mb-2 text-base font-semibold first:mt-0"),
  h4: styled("h4", "mt-4 mb-1.5 text-base font-medium first:mt-0"),
  p: styled("p", "my-2.5 first:mt-0 last:mb-0"),
  ul: styled("ul", "my-2.5 list-disc pl-5"),
  ol: styled("ol", "my-2.5 list-decimal pl-5"),
  li: styled("li", "my-1 pl-0.5 marker:text-subtle"),
  strong: styled("strong", "font-semibold"),
  blockquote: styled("blockquote", "my-3 border-l-2 border-line pl-3 text-muted"),
  hr: styled("hr", "my-5 border-line"),
  code: styled("code", "rounded-sm bg-surface-sunken px-1 py-0.5 font-mono text-[0.9em]"),
  pre: styled(
    "pre",
    "my-3 overflow-x-auto rounded-md bg-surface-sunken p-3 text-sm [&_code]:bg-transparent [&_code]:p-0",
  ),
  a: ({ node, ...rest }) => {
    void node;
    return <a className="text-accent underline" target="_blank" rel="noreferrer" {...rest} />;
  },
  table: ({ node, ...rest }) => {
    void node;
    return (
      <div className="my-3 overflow-x-auto rounded-md border border-line">
        <table className="w-full border-collapse text-sm" {...rest} />
      </div>
    );
  },
  thead: styled("thead", "bg-surface-sunken"),
  th: styled("th", "border-b border-line px-3 py-2 text-left font-semibold whitespace-nowrap"),
  td: styled("td", "border-t border-line px-3 py-2 align-top first:whitespace-nowrap"),
};

export function Markdown({
  children,
  className,
  breaks,
}: {
  children: string;
  className?: string;
  /** 줄바꿈 한 번도 줄로 살린다. 동료가 쓴 문서는 Markdown이 아닌 평문 줄바꿈이 많다 */
  breaks?: boolean;
}) {
  return (
    <div className={cn("break-words break-keep", className)}>
      <ReactMarkdown
        remarkPlugins={breaks ? [remarkGfm, remarkBreaks] : [remarkGfm]}
        skipHtml
        components={COMPONENTS}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
