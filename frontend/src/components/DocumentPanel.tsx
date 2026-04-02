import {
  type DragEvent,
  type ChangeEvent,
  useCallback,
  useRef,
  useState,
} from 'react';
import type { Document } from '../api/client';

interface DocumentPanelProps {
  documents: Document[];
  isLoading: boolean;
  uploadProgress: number | null;
  error: string | null;
  onUpload: (file: File) => Promise<void>;
  onDelete: (docId: string) => Promise<void>;
  onRefresh: () => void;
}

export default function DocumentPanel({
  documents,
  isLoading,
  uploadProgress,
  error,
  onUpload,
  onDelete,
  onRefresh,
}: DocumentPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // ── Drag & Drop ──────────────────────────────────────────────────────────

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    // Only fire when we leave the drop zone itself (not child elements)
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDragging(false);
  };

  const handleDrop = useCallback(
    async (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (!file) return;
      setUploadError(null);
      try {
        await onUpload(file);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Upload failed');
      }
    },
    [onUpload],
  );

  // ── File input ───────────────────────────────────────────────────────────

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploadError(null);
      try {
        await onUpload(file);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Upload failed');
      } finally {
        // Reset so the same file can be re-uploaded
        e.target.value = '';
      }
    },
    [onUpload],
  );

  // ── Delete flow (two-step confirm) ───────────────────────────────────────

  const handleDeleteClick = (docId: string) => {
    setPendingDelete(docId);
  };

  const handleDeleteConfirm = useCallback(
    async (docId: string) => {
      setPendingDelete(null);
      try {
        await onDelete(docId);
      } catch {
        // Error is surfaced via the error prop from useDocuments
      }
    },
    [onDelete],
  );

  const handleDeleteCancel = () => setPendingDelete(null);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <aside className="doc-panel">
      <div className="doc-panel__header">
        <h2 className="doc-panel__title">Documents</h2>
        <button
          className="doc-panel__refresh"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="Refresh document list"
          title="Refresh"
        >
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M17.65 6.35A7.96 7.96 0 0 0 12 4C7.58 4 4 7.58 4 12s3.58 8 8 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />
          </svg>
        </button>
      </div>

      {/* Drop zone / upload area */}
      <div
        className={`doc-panel__dropzone ${isDragging ? 'doc-panel__dropzone--active' : ''} ${uploadProgress !== null ? 'doc-panel__dropzone--uploading' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="region"
        aria-label="File drop zone"
      >
        {uploadProgress !== null ? (
          <div className="upload-progress" aria-live="polite">
            <div className="upload-progress__bar">
              <div
                className="upload-progress__fill"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className="upload-progress__label">{uploadProgress}%</span>
          </div>
        ) : (
          <>
            <svg
              className="doc-panel__dropzone-icon"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z" />
            </svg>
            <p className="doc-panel__dropzone-text">
              {isDragging ? 'Drop to upload' : 'Drag & drop a file or'}
            </p>
            {!isDragging && (
              <button
                className="doc-panel__upload-btn"
                onClick={() => fileInputRef.current?.click()}
              >
                Choose file
              </button>
            )}
          </>
        )}
      </div>

      {/* Hidden real file input */}
      <input
        ref={fileInputRef}
        type="file"
        className="visually-hidden"
        onChange={handleFileChange}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Error messages */}
      {(error || uploadError) && (
        <p className="doc-panel__error" role="alert">
          ⚠️ {uploadError ?? error}
        </p>
      )}

      {/* Document list */}
      {isLoading && documents.length === 0 ? (
        <div className="doc-panel__loading" aria-live="polite">
          <span className="spinner" />
          <span className="visually-hidden">Loading documents…</span>
        </div>
      ) : documents.length === 0 ? (
        <p className="doc-panel__empty">No documents uploaded yet.</p>
      ) : (
        <ul className="doc-list" role="list">
          {documents.map((doc) => (
            <li key={doc.doc_id} className="doc-list__item">
              <div className="doc-list__info">
                <span className="doc-list__filename" title={doc.filename}>
                  {doc.filename}
                </span>
                <span className="doc-list__chunks">
                  {doc.chunks_count} chunk{doc.chunks_count !== 1 ? 's' : ''}
                </span>
              </div>

              {pendingDelete === doc.doc_id ? (
                <div className="doc-list__confirm" role="group" aria-label="Confirm delete">
                  <span className="doc-list__confirm-text">Delete?</span>
                  <button
                    className="doc-list__confirm-yes"
                    onClick={() => handleDeleteConfirm(doc.doc_id)}
                    aria-label="Confirm delete"
                  >
                    Yes
                  </button>
                  <button
                    className="doc-list__confirm-no"
                    onClick={handleDeleteCancel}
                    aria-label="Cancel delete"
                  >
                    No
                  </button>
                </div>
              ) : (
                <button
                  className="doc-list__delete"
                  onClick={() => handleDeleteClick(doc.doc_id)}
                  aria-label={`Delete ${doc.filename}`}
                  title="Delete document"
                >
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" />
                  </svg>
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
