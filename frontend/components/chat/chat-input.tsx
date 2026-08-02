"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ChatInputProps = {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
};

export function ChatInput({
  onSend,
  onStop,
  streaming,
  disabled = false,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
    }
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={
          streaming
            ? "Assistant is responding…"
            : "Ask about your router, e.g. “What is my WAN IP?”"
        }
        rows={1}
        aria-label="Chat message"
        className={cn(
          "max-h-[180px] min-h-10 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-[border,box-shadow] focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          disabled && "opacity-60",
        )}
      />
      {streaming ? (
        <Button
          onClick={onStop}
          variant="outline"
          size="icon"
          aria-label="Stop streaming"
          className="shrink-0"
        >
          <Square className="size-4" aria-hidden />
        </Button>
      ) : (
        <Button
          onClick={submit}
          size="icon"
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          className="shrink-0"
        >
          <Send className="size-4" aria-hidden />
        </Button>
      )}
    </div>
  );
}
