import { useCallback, useEffect, useState } from 'react';
import {
  deleteDocument as apiDelete,
  listDocuments,
  uploadDocument as apiUpload,
} from '../api/client';
import type { Document } from '../api/client';

// ─── Types ────────────────────────────────────────────────────────────────────

interface UseDocumentsReturn {
  documents: Document[];
  isLoading: boolean;
  uploadProgress: number | null; // 0-100 while uploading, null otherwise
  error: string | null;
  fetchDocuments: () => Promise<void>;
  uploadDocument: (file: File) => Promise<void>;
  deleteDocument: (docId: string) => Promise<void>;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useDocuments(): UseDocumentsReturn {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch documents');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const uploadDocument = useCallback(
    async (file: File) => {
      setError(null);
      setUploadProgress(0);
      try {
        const result = await apiUpload(file, (pct) => setUploadProgress(pct));
        // Optimistically add the new doc then refresh for consistency
        setDocuments((prev) => [
          ...prev,
          {
            doc_id: result.doc_id,
            filename: result.filename,
            chunks_count: result.chunks_count,
          },
        ]);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
        throw err; // re-throw so the UI can handle it
      } finally {
        setUploadProgress(null);
      }
    },
    [],
  );

  const deleteDocument = useCallback(async (docId: string) => {
    setError(null);
    try {
      await apiDelete(docId);
      setDocuments((prev) => prev.filter((d) => d.doc_id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
      throw err;
    }
  }, []);

  // Fetch documents on mount
  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  return {
    documents,
    isLoading,
    uploadProgress,
    error,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
  };
}
