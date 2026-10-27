"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getErrorMessage,
  getMessages,
  queryNotebook,
  type ChatMessage,
  type Citation,
} from "@/lib/api";

type MetaEvent = {
  conversation_id: string;
  user_message_id: string;
  citations: Citation[];
};

type CitationsEvent = { citations: Citation[] };
type TokenEvent = { text: string };
type DoneEvent = {
  message_id: string;
  content: string;
  citations: Citation[];
  model: string | null;
};
type ErrorEvent = { message: string };

type SseEvent = { event: string; data: unknown };

async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  const reader = response.body?.getReader();

  if (!reader) {
    throw new Error("The answer stream is unavailable.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let event = "message";
      let data = "";

      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) {
          event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          data += line.slice(5).trim();
        }
      }

      if (data) {
        yield { event, data: JSON.parse(data) as unknown };
      }

      boundary = buffer.indexOf("\n\n");
    }
  }
}

export function useChat(notebookId: string) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    let cancelled = false;

    getMessages(notebookId)
      .then((history) => {
        if (!cancelled) {
          setMessages(history);
          setLoadError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setLoadError(getErrorMessage(caught));
        }
      });

    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [notebookId, reloadKey]);

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();

      if (!trimmed || streaming) {
        return;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      setChatError(null);
      setStreaming(true);

      const now = new Date().toISOString();
      const userId = `local-user-${Date.now()}`;
      const assistantId = `local-assistant-${Date.now()}`;

      setMessages((current) => [
        ...(current ?? []),
        {
          id: userId,
          role: "user",
          content: trimmed,
          citations: null,
          model: null,
          created_at: now,
        },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          citations: null,
          model: null,
          created_at: now,
        },
      ]);

      try {
        const response = await queryNotebook(
          notebookId,
          trimmed,
          controller.signal,
        );

        for await (const event of readSse(response)) {
          if (event.event === "meta") {
            const data = event.data as MetaEvent;
            setMessages(
              (current) =>
                current?.map((message) =>
                  message.id === userId
                    ? { ...message, id: data.user_message_id }
                    : message.id === assistantId
                      ? { ...message, citations: data.citations }
                      : message,
                ) ?? current,
            );
          } else if (event.event === "citations") {
            const data = event.data as CitationsEvent;
            setMessages(
              (current) =>
                current?.map((message) =>
                  message.id === assistantId
                    ? { ...message, citations: data.citations }
                    : message,
                ) ?? current,
            );
          } else if (event.event === "token") {
            const data = event.data as TokenEvent;
            setMessages(
              (current) =>
                current?.map((message) =>
                  message.id === assistantId
                    ? { ...message, content: message.content + data.text }
                    : message,
                ) ?? current,
            );
          } else if (event.event === "done") {
            const data = event.data as DoneEvent;
            setMessages(
              (current) =>
                current?.map((message) =>
                  message.id === assistantId
                    ? {
                        ...message,
                        id: data.message_id,
                        content: data.content,
                        citations: data.citations,
                        model: data.model,
                      }
                    : message,
                ) ?? current,
            );
          } else if (event.event === "error") {
            const data = event.data as ErrorEvent;
            setChatError(data.message);
            setMessages(
              (current) =>
                current?.flatMap((message) =>
                  message.id === assistantId && !message.content
                    ? []
                    : [message],
                ) ?? current,
            );
          }
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setChatError(getErrorMessage(caught));
          setMessages(
            (current) =>
              current?.flatMap((message) =>
                message.id === assistantId && !message.content
                  ? []
                  : [message],
              ) ?? current,
          );
        } else {
          setMessages(
            (current) =>
              current?.flatMap((message) =>
                message.id === assistantId && !message.content
                  ? []
                  : [message],
              ) ?? current,
          );
        }
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        setStreaming(false);
      }
    },
    [notebookId, streaming],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    messages,
    streaming,
    loadError,
    chatError,
    send,
    stop,
    reload,
    clearChatError: () => setChatError(null),
  };
}
