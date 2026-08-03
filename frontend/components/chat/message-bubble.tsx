"use client";

import { useState } from "react";
import { Bot, ChevronDown, ChevronRight, User } from "lucide-react";

import { Markdown } from "@/components/chat/markdown";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
  provider: string | null;
  model: string | null;
  streaming?: boolean;
  routerContext?: string | null;
};

function Cursor() {
  return (
    <span
      className="ml-0.5 inline-block h-4 w-[2px] animate-pulse rounded-full bg-muted-foreground align-middle"
      aria-hidden
    />
  );
}

function RouterContextPanel({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="w-full rounded-xl border bg-card text-card-foreground shadow-xs">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-1 px-4 py-2 text-left text-sm font-medium"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="size-4" aria-hidden />
        ) : (
          <ChevronRight className="size-4" aria-hidden />
        )}
        Router Context
      </button>
      {expanded ? (
        <div className="border-t px-4 py-2.5 text-sm">
          <Markdown content={content} />
        </div>
      ) : null}
    </div>
  );
}

export function MessageBubble({
  role,
  content,
  provider,
  model,
  streaming = false,
  routerContext = null,
}: MessageBubbleProps) {
  const isUser = role === "user";
  return (
    <div
      className={cn(
        "flex w-full gap-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser ? (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-muted/60">
          <Bot className="size-4" aria-hidden />
        </div>
      ) : null}
      <div
        className={cn(
          "flex max-w-[82%] flex-col gap-1.5",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "rounded-xl px-4 py-2.5 text-sm shadow-xs",
            isUser
              ? "bg-primary text-primary-foreground"
              : "border bg-card text-card-foreground",
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{content}</p>
          ) : content ? (
            <Markdown content={content} />
          ) : streaming ? (
            <p className="text-muted-foreground">Thinking…</p>
          ) : null}
          {!isUser && streaming && content ? <Cursor /> : null}
        </div>
        {!isUser && (provider || model) ? (
          <Badge variant="outline" className="text-[10px] text-muted-foreground">
            {provider ?? "provider"}
            {model ? ` · ${model}` : ""}
          </Badge>
        ) : null}
        {!isUser && routerContext ? <RouterContextPanel content={routerContext} /> : null}
      </div>
      {isUser ? (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-primary/10">
          <User className="size-4" aria-hidden />
        </div>
      ) : null}
    </div>
  );
}
