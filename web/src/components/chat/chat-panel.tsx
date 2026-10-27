"use client";

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import {
  Loader2Icon,
  MessageSquareIcon,
  RefreshCwIcon,
  SendIcon,
  SparklesIcon,
  SquareIcon,
  XIcon,
} from "lucide-react";

import { Markdown } from "@/components/chat/markdown";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import type { ChatMessage, Citation } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";

type ChatPanelProps = {
  notebookId: string;
  readySourceCount: number;
  onCitation: (citation: Citation) => void;
};

function AssistantMessage({
  message,
  streaming,
  onCitation,
}: {
  message: ChatMessage;
  streaming: boolean;
  onCitation: (citation: Citation) => void;
}) {
  const citations = message.citations ?? [];

  return (
    <div className="flex gap-2.5">
      <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <SparklesIcon className="size-3.5 text-primary" />
      </div>
      <div className="min-w-0 flex-1 text-sm">
        {message.content ? (
          <Markdown
            content={message.content}
            citations={message.citations}
            onCitation={onCitation}
          />
        ) : streaming ? (
          <p className="flex items-center gap-2 text-muted-foreground">
            <Loader2Icon className="size-3.5 animate-spin" />
            Searching your sources...
          </p>
        ) : null}

        {citations.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5 border-t pt-2.5">
            {citations.map((citation) => (
              <button
                key={`${citation.index}-${citation.source_id}`}
                type="button"
                onClick={() => onCitation(citation)}
                title={citation.snippet}
                className="inline-flex max-w-full items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <span className="font-semibold text-primary">
                  [{citation.index}]
                </span>
                <span className="max-w-40 truncate">
                  {citation.source_title}
                </span>
                {citation.page ? (
                  <span>p.{citation.page}</span>
                ) : citation.start_seconds !== null &&
                  citation.start_seconds !== undefined ? (
                  <span>{formatTimestamp(citation.start_seconds)}</span>
                ) : null}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ChatPanel({
  notebookId,
  readySourceCount,
  onCitation,
}: ChatPanelProps) {
  const {
    messages,
    streaming,
    loadError,
    chatError,
    send,
    stop,
    reload,
    clearChatError,
  } = useChat(notebookId);
  const [question, setQuestion] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, streaming]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();

    if (!trimmed || streaming) {
      return;
    }

    setQuestion("");
    void send(trimmed);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <section className="flex h-[min(72vh,760px)] min-h-96 flex-col rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-medium">Chat</h2>
        <span className="text-xs text-muted-foreground">
          {streaming
            ? "Answering..."
            : `${messages?.length ?? 0} messages`}
        </span>
      </div>

      {loadError && (
        <div className="flex items-center justify-between gap-2 border-b bg-destructive/5 px-4 py-2 text-xs text-destructive">
          <span className="min-w-0 truncate">{loadError}</span>
          <Button size="xs" variant="ghost" onClick={reload}>
            <RefreshCwIcon />
            Retry
          </Button>
        </div>
      )}

      {messages === null ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
          <Loader2Icon className="size-5 animate-spin" />
          <p className="text-xs">Loading conversation...</p>
        </div>
      ) : messages.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 py-12 text-center">
          <div className="flex size-11 items-center justify-center rounded-full bg-muted">
            <MessageSquareIcon className="size-5 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">Grounded answers will appear here</p>
          <p className="max-w-sm text-xs text-muted-foreground">
            Ask a question about your sources. Every answer cites the exact
            passage it came from.
          </p>
        </div>
      ) : (
        <div
          className="flex-1 space-y-5 overflow-y-auto px-4 py-4"
          role="log"
          aria-live="polite"
        >
          {messages.map((message) =>
            message.role === "user" ? (
              <div
                key={message.id}
                className="ml-auto max-w-[85%] rounded-xl bg-muted px-3 py-2 text-sm whitespace-pre-wrap"
              >
                {message.content}
              </div>
            ) : (
              <AssistantMessage
                key={message.id}
                message={message}
                streaming={streaming}
                onCitation={onCitation}
              />
            ),
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {chatError && (
        <div className="flex items-center justify-between gap-2 border-t bg-destructive/5 px-4 py-2 text-xs text-destructive">
          <span className="min-w-0">{chatError}</span>
          <button
            type="button"
            aria-label="Dismiss error"
            onClick={clearChatError}
            className="rounded p-1 hover:bg-destructive/10"
          >
            <XIcon className="size-3.5" />
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="border-t p-3">
        <div className="flex items-end gap-2 rounded-lg border bg-background p-1.5 pl-3 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your sources..."
            aria-label="Ask a question"
            rows={1}
            maxLength={2000}
            className="max-h-32 min-h-9 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground"
          />
          {streaming ? (
            <Button type="button" size="sm" variant="outline" onClick={stop}>
              <SquareIcon />
              Stop
            </Button>
          ) : (
            <Button type="submit" size="sm" disabled={!question.trim()}>
              <SendIcon />
              Send
            </Button>
          )}
        </div>
        <p className="mt-1.5 px-1 text-[11px] text-muted-foreground">
          {readySourceCount === 0
            ? "No indexed sources yet. Add a source to ground the answer."
            : `Answers can cite ${readySourceCount} ready source${
                readySourceCount === 1 ? "" : "s"
              }.`}
        </p>
      </form>
    </section>
  );
}
