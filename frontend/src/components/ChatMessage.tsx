import { useState } from 'react';
import type { ChatMessage } from '../hooks/useChat';
import FeedbackWidget from './FeedbackWidget';

interface ChatMessageProps {
  message: ChatMessage;
}

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
          {message.content}
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
