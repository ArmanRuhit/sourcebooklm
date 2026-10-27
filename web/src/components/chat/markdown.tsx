"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CitationChip } from "@/components/chat/citation-chip";
import type { Citation } from "@/lib/api";

function linkifyCitations(content: string): string {
  return content.replace(/\[(\d+)\](?!\()/g, "[$1](#citation-$1)");
}

type MarkdownProps = {
  content: string;
  citations: Citation[] | null;
  onCitation: (citation: Citation) => void;
};

export function Markdown({ content, citations, onCitation }: MarkdownProps) {
  const components: Components = {
    p: ({ children }) => (
      <p className="mb-2 leading-relaxed last:mb-0">{children}</p>
    ),
    ul: ({ children }) => (
      <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
    ),
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    h1: ({ children }) => (
      <h3 className="mb-2 font-heading text-base font-semibold">{children}</h3>
    ),
    h2: ({ children }) => (
      <h4 className="mb-2 font-heading text-sm font-semibold">{children}</h4>
    ),
    h3: ({ children }) => (
      <h5 className="mb-1.5 font-heading text-sm font-medium">{children}</h5>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold">{children}</strong>
    ),
    pre: ({ children }) => (
      <pre className="mb-2 overflow-x-auto rounded-md bg-muted p-3 text-xs">
        {children}
      </pre>
    ),
    code: ({ className, children }) =>
      className ? (
        <code className={className}>{children}</code>
      ) : (
        <code className="rounded bg-muted px-1 py-0.5 text-[0.85em]">
          {children}
        </code>
      ),
    a: ({ href, children }) => {
      const match = /^#citation-(\d+)$/.exec(href ?? "");

      if (match) {
        const citation = citations?.find(
          (item) => item.index === Number(match[1]),
        );

        if (citation) {
          return (
            <CitationChip citation={citation} onSelect={onCitation} />
          );
        }
      }

      return (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-foreground"
        >
          {children}
        </a>
      );
    },
  };

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {linkifyCitations(content)}
    </ReactMarkdown>
  );
}
