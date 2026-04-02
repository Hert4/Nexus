// ─── Types ────────────────────────────────────────────────────────────────────

export interface Source {
  filename: string;
  snippet: string;
  chunk_index: number;
}

export interface ChatResponse {
  message_id: string;
  answer: string;
  sources: Source[];
}

export interface Document {
  doc_id: string;
  filename: string;
  chunks_count: number;
}

export interface UploadResponse {
  doc_id: string;
  filename: string;
  chunks_count: number;
  message: string;
}

export interface FeedbackPayload {
  message_id: string;
  rating: number;
  comment?: string;
}

export interface AgentResult {
  task: string;
  final_answer: string;
  steps_taken: number;
  tool_results: unknown[];
}

export interface ServiceStatus {
  status: 'ok' | 'degraded' | 'error';
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  services: {
    llamacpp_chat: ServiceStatus | string;
    llamacpp_embed: ServiceStatus | string;
    qdrant: ServiceStatus | string;
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const BASE = '/v1';

async function throwOnError(res: Response): Promise<void> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

/**
 * Streaming chat via SSE. Calls onChunk for every text chunk, onDone when
 * [DONE] is received. Returns the message_id from the X-Message-ID header
 * (resolved as soon as the response headers arrive).
 */
export async function streamChat(
  message: string,
  useRag: boolean,
  sessionId: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, stream: true, use_rag: useRag, session_id: sessionId }),
    signal,
  });

  await throwOnError(res);

  const messageId = res.headers.get('X-Message-ID') ?? '';

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by double newlines
    const parts = buffer.split('\n\n');
    // The last part may be incomplete – keep it in the buffer
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      // Each part may contain multiple lines; find the data: line
      for (const line of part.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();

        if (payload === '[DONE]') {
          onDone();
          return messageId;
        }

        try {
          const parsed = JSON.parse(payload) as { chunk?: string };
          if (parsed.chunk !== undefined) {
            onChunk(parsed.chunk);
          }
        } catch {
          // Malformed JSON – skip silently
        }
      }
    }
  }

  // Stream ended without explicit [DONE] – still fire onDone
  onDone();
  return messageId;
}

/**
 * Non-streaming chat – returns the full answer plus sources.
 */
export async function chat(
  message: string,
  useRag: boolean,
  sessionId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      stream: false,
      use_rag: useRag,
      session_id: sessionId ?? '',
    }),
  });
  await throwOnError(res);
  return res.json() as Promise<ChatResponse>;
}

// ─── Documents ────────────────────────────────────────────────────────────────

export async function uploadDocument(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('file', file);

    xhr.open('POST', `${BASE}/documents`);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
        } catch {
          reject(new Error('Invalid JSON response from upload'));
        }
      } else {
        let detail = xhr.statusText;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string; message?: string };
          detail = body.detail ?? body.message ?? detail;
        } catch {
          // ignore
        }
        reject(new Error(`HTTP ${xhr.status}: ${detail}`));
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.onabort = () => reject(new Error('Upload aborted'));

    xhr.send(form);
  });
}

export async function listDocuments(): Promise<Document[]> {
  const res = await fetch(`${BASE}/documents`);
  await throwOnError(res);
  return res.json() as Promise<Document[]>;
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await fetch(`${BASE}/documents/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
  });
  if (res.status === 204) return;
  await throwOnError(res);
}

// ─── Feedback ─────────────────────────────────────────────────────────────────

export async function submitFeedback(
  messageId: string,
  rating: number,
  comment?: string,
): Promise<void> {
  const payload: FeedbackPayload = { message_id: messageId, rating };
  if (comment) payload.comment = comment;

  const res = await fetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (res.status === 201) return;
  await throwOnError(res);
}

// ─── Agents ───────────────────────────────────────────────────────────────────

export async function runAgent(task: string): Promise<AgentResult> {
  const res = await fetch(`${BASE}/agents/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }),
  });
  await throwOnError(res);
  return res.json() as Promise<AgentResult>;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch('/health');
  await throwOnError(res);
  return res.json() as Promise<HealthResponse>;
}
