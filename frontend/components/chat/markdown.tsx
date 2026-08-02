"use client";

import type { ComponentProps, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type CodeProps = ComponentProps<"code"> & { node?: { type?: string } };
type PreProps = ComponentProps<"pre"> & { node?: unknown };

function CodeBlock({ className, children, node }: CodeProps) {
  const inline = node?.type === "inlineCode";
  if (inline) {
    return (
      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[13px]">
        {children}
      </code>
    );
  }
  return (
    <code className={className ?? "font-mono text-[13px]"} dir="ltr">
      {children}
    </code>
  );
}

function PreBlock({ children }: PreProps) {
  return (
    <pre className="my-3 overflow-x-auto rounded-lg border border-border bg-muted/60 p-3 text-[13px] leading-relaxed text-foreground">
      {children}
    </pre>
  );
}

/**
 * Renders assistant markdown (headings, lists, inline code, fenced code blocks,
 * tables via GFM). Sanitized by react-markdown's default escape handling —
 * raw HTML in model output is not rendered.
 */
export function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown-body space-y-2 text-[15px] leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: CodeBlock,
          pre: PreBlock,
          a: ({ children, ...props }) => (
            <a
              {...props}
              className="text-primary underline underline-offset-4 hover:opacity-80"
              target="_blank"
              rel="noreferrer"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="list-disc space-y-1 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-1 pl-5">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          h1: ({ children }) => (
            <h1 className="text-lg font-semibold tracking-tight">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold tracking-tight">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[15px] font-semibold">{children}</h3>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-muted-foreground/40 pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-border px-2 py-1 text-left font-medium">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-2 py-1">{children}</td>
          ),
          strong: ({ children }: { children?: ReactNode }) => (
            <strong className="font-semibold">{children}</strong>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
