import { useCallback, useRef, useState } from 'react';
import { streamChat } from '../api/client';
import type { Source } from '../api/client';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
  /** Backend message ID used for feedback */
  messageId?: string;
}

interface UseChatReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (text: string, useRag: boolean) => Promise<void>;
  clearMessages: () => void;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

let _localIdCounter = 0;
function localId(): string {
  return `local-${Date.now()}-${_localIdCounter++}`;
}

// A single, stable session ID for the lifetime of this page
const SESSION_ID = crypto.randomUUID();

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Keep an AbortController so we can cancel in-flight requests
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (text: string, useRag: boolean) => {
    if (!text.trim()) return;

    // Cancel any previous in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setError(null);
    setIsLoading(true);

    // 1. Append the user message immediately
    const userMsgId = localId();
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: 'user', content: text },
    ]);

    // 2. Append a placeholder assistant message that will be updated per-chunk
    const assistantMsgId = localId();
    setMessages((prev) => [
      ...prev,
      { id: assistantMsgId, role: 'assistant', content: '', isStreaming: true },
    ]);

    try {
      const backendMessageId = await streamChat(
        text,
        useRag,
        SESSION_ID,
        // onChunk – append text incrementally
        (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: m.content + chunk }
                : m,
            ),
          );
        },
        // onDone – mark streaming finished
        () => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, isStreaming: false } : m,
            ),
          );
          setIsLoading(false);
        },
        controller.signal,
      );

      // Store the backend message ID so FeedbackWidget can reference it
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId ? { ...m, messageId: backendMessageId } : m,
        ),
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // User cancelled – clean up the streaming placeholder
        setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
      } else {
        const msg = err instanceof Error ? err.message : 'Unknown error';
        setError(msg);
        // Replace placeholder with error notice
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: `⚠️ ${msg}`, isStreaming: false }
              : m,
          ),
        );
      }
      setIsLoading(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
    setIsLoading(false);
  }, []);

  return { messages, isLoading, error, sendMessage, clearMessages };
}
