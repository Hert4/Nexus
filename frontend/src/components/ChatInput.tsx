import {
  type ChangeEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

interface ChatInputProps {
  onSend: (text: string, useRag: boolean) => void;
  isLoading: boolean;
}

export default function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [value, setValue] = useState('');
  const [useRag, setUseRag] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea up to 5 rows
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const lineHeight = parseInt(getComputedStyle(el).lineHeight, 10) || 20;
    const maxHeight = lineHeight * 5;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed, useRag);
    setValue('');
  };

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <div className="chat-input-wrapper">
      <div className="chat-input-toolbar">
        <label className="rag-toggle">
          <input
            type="checkbox"
            checked={useRag}
            onChange={(e) => setUseRag(e.target.checked)}
            aria-label="Use RAG"
          />
          <span className="rag-toggle__label">RAG</span>
        </label>
      </div>

      <div className="chat-input-row">
        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask Nexus anything… (Enter to send, Shift+Enter for new line)"
          rows={1}
          disabled={isLoading}
          aria-label="Chat message"
        />
        <button
          className="chat-input__send"
          onClick={submit}
          disabled={!canSend}
          aria-label="Send message"
          title="Send (Enter)"
        >
          {isLoading ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
