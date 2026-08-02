"use client";

import { Bot, User } from "lucide-react";

import { Markdown } from "@/components/chat/markdown";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
  provider: string | null;
  model: string | null;
  streaming?: boolean;
};

function Cursor() {
  return (
    <span
      className="ml-0.5 inline-block h-4 w-[2px] animate-pulse rounded-full bg-muted-foreground align-middle"
      aria-hidden
    />
  );
}

export function MessageBubble({
  role,
  content,
  provider,
  model,
  streaming = false,
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
      </div>
      {isUser ? (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-primary/10">
          <User className="size-4" aria-hidden />
        </div>
      ) : null}
    </div>
  );
}
