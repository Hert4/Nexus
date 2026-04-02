import { useState } from 'react';
import type { ChatMessage } from '../hooks/useChat';
import FeedbackWidget from './FeedbackWidget';

interface ChatMessageProps {
  message: ChatMessage;
}

// ── Simple markdown renderer ───────────────────────────────────────────────
// Supports: fenced code blocks (```lang\n...\n```), inline `code`, **bold**, *italic*
// Returns an array of React nodes.
function renderMarkdown(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // Split on fenced code blocks
  const fencedRe = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = fencedRe.exec(text)) !== null) {
    // Text before the code block
    if (match.index > lastIndex) {
      nodes.push(...renderInline(text.slice(lastIndex, match.index), nodes.length));
    }
    // Code block
    const lang = match[1] || '';
    const code = match[2].replace(/\n$/, ''); // trim trailing newline
    nodes.push(
      <div key={`cb-${match.index}`} className="code-block">
        {lang && <span className="code-block__lang">{lang}</span>}
        <pre className="code-block__pre"><code>{code}</code></pre>
      </div>,
    );
    lastIndex = fencedRe.lastIndex;
  }

  // Remaining text
  if (lastIndex < text.length) {
    nodes.push(...renderInline(text.slice(lastIndex), nodes.length));
  }

  return nodes;
}

function renderInline(text: string, baseKey: number): React.ReactNode[] {
  // Split on inline code, **bold**, *italic*
  const parts: React.ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith('`')) {
      parts.push(<code key={`ic-${baseKey}-${m.index}`} className="inline-code">{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**')) {
      parts.push(<strong key={`b-${baseKey}-${m.index}`}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<em key={`i-${baseKey}-${m.index}`}>{token.slice(1, -1)}</em>);
    }
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));

  // Wrap in a paragraph preserving newlines
  return [<span key={`p-${baseKey}`} className="text-para">{parts}</span>];
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatMessageBubble({ message }: ChatMessageProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const isUser = message.role === 'user';

  return (
    <div className={`chat-message ${isUser ? 'chat-message--user' : 'chat-message--assistant'}`}>
      <div className="chat-bubble">
        {/* Avatar label */}
        <span className="chat-bubble__role">
          {isUser ? 'You' : '🤖 Nexus'}
        </span>

        {/* Message text */}
        <div className="chat-bubble__text">
          {isUser
            ? message.content
            : renderMarkdown(message.content)}
          {message.isStreaming && <span className="cursor-blink" aria-hidden="true" />}
        </div>

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="chat-bubble__sources">
            <button
              className="sources-toggle"
              onClick={() => setSourcesOpen((o) => !o)}
              aria-expanded={sourcesOpen}
            >
              📎 {sourcesOpen ? 'Hide' : 'Show'} {message.sources.length} source
              {message.sources.length !== 1 ? 's' : ''}
            </button>
            {sourcesOpen && (
              <ul className="sources-list" role="list">
                {message.sources.map((src, i) => (
                  <li key={i} className="source-item">
                    <span className="source-item__filename">{src.filename}</span>
                    <span className="source-item__chunk">chunk #{src.chunk_index}</span>
                    <blockquote className="source-item__snippet">{src.snippet}</blockquote>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Feedback (only for completed assistant messages that have a backend ID) */}
        {!isUser && !message.isStreaming && message.messageId && (
          <FeedbackWidget messageId={message.messageId} />
        )}
      </div>
    </div>
  );
}
