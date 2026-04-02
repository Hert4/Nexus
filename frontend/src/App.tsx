import { useEffect, useRef, useState } from 'react';
import ChatInput from './components/ChatInput';
import ChatMessageBubble from './components/ChatMessage';
import DocumentPanel from './components/DocumentPanel';
import HealthBadge from './components/HealthBadge';
import { useChat } from './hooks/useChat';
import { useDocuments } from './hooks/useDocuments';

export default function App() {
  const { messages, isLoading, error, sendMessage, clearMessages } = useChat();
  const {
    documents,
    isLoading: docsLoading,
    uploadProgress,
    error: docsError,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
  } = useDocuments();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="app">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="app-header">
        <div className="app-header__left">
          <span className="app-header__logo" aria-hidden="true">🤖</span>
          <h1 className="app-header__title">Nexus AI</h1>
        </div>

        <div className="app-header__right">
          <HealthBadge />
          <button
            className={`app-header__docs-toggle ${sidebarOpen ? 'app-header__docs-toggle--active' : ''}`}
            onClick={() => setSidebarOpen((v) => !v)}
            aria-expanded={sidebarOpen}
            aria-controls="doc-sidebar"
            title={sidebarOpen ? 'Hide Documents' : 'Show Documents'}
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z" />
            </svg>
            Docs
            <svg
              className={`app-header__chevron ${sidebarOpen ? 'app-header__chevron--open' : ''}`}
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z" />
            </svg>
          </button>

          {messages.length > 0 && (
            <button
              className="app-header__clear"
              onClick={clearMessages}
              title="Clear conversation"
              aria-label="Clear conversation"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM8 9h8v10H8V9zm7.5-5-1-1h-5l-1 1H5v2h14V4z" />
              </svg>
            </button>
          )}
        </div>
      </header>

      {/* ── Main content ───────────────────────────────────────────────────── */}
      <div className="app-body">
        {/* Sidebar */}
        <div
          id="doc-sidebar"
          className={`app-sidebar ${sidebarOpen ? 'app-sidebar--open' : 'app-sidebar--closed'}`}
          aria-hidden={!sidebarOpen}
        >
          <DocumentPanel
            documents={documents}
            isLoading={docsLoading}
            uploadProgress={uploadProgress}
            error={docsError}
            onUpload={uploadDocument}
            onDelete={deleteDocument}
            onRefresh={fetchDocuments}
          />
        </div>

        {/* Chat area */}
        <main className="app-chat">
          {/* Messages */}
          <div className="chat-messages" role="log" aria-live="polite" aria-label="Conversation">
            {messages.length === 0 && (
              <div className="chat-empty">
                <span className="chat-empty__icon" aria-hidden="true">💬</span>
                <p className="chat-empty__text">
                  Start a conversation with Nexus AI. Toggle RAG to include your uploaded documents as context.
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <ChatMessageBubble key={msg.id} message={msg} />
            ))}

            {/* Global error banner */}
            {error && (
              <div className="chat-error" role="alert">
                ⚠️ {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="chat-footer">
            <ChatInput onSend={sendMessage} isLoading={isLoading} />
          </div>
        </main>
      </div>
    </div>
  );
}
