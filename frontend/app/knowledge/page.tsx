"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { UploadCloud } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { DocumentRow } from "@/components/knowledge/document-row";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, documentsApi, type DocumentRecord } from "@/lib/api";

const POLL_INTERVAL_MS = 4000;

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshDocuments = useCallback(async () => {
    try {
      const result = await documentsApi.list();
      setDocuments(result);
    } catch (error) {
      if (error instanceof ApiError) toast.error(error.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Deferred via microtask so no setState call happens synchronously within the effect body.
    void Promise.resolve().then(refreshDocuments);
  }, [refreshDocuments]);

  useEffect(() => {
    const hasInFlight = documents.some((d) => d.status === "pending" || d.status === "processing");
    if (!hasInFlight) return;
    const interval = setInterval(refreshDocuments, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [documents, refreshDocuments]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error(`${file.name} is not a PDF file.`);
        continue;
      }
      try {
        const document = await documentsApi.upload(file);
        toast.success(`${document.filename} queued for processing.`);
        setDocuments((prev) => [document, ...prev]);
      } catch (error) {
        toast.error(error instanceof ApiError ? error.message : `Failed to upload ${file.name}.`);
      }
    }
  }

  return (
    <AppShell>
      <div className="flex flex-1 flex-col overflow-y-auto px-6 py-6">
        <header className="mb-6">
          <h1 className="text-lg font-semibold">Knowledge base</h1>
          <p className="text-sm text-muted-foreground">
            Upload company PDFs to chunk, embed, and index them for grounded Q&amp;A.
          </p>
        </header>

        <div className="mx-auto w-full max-w-3xl space-y-6">
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              handleFiles(event.dataTransfer.files);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors ${
              isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"
            }`}
          >
            <UploadCloud className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">Drag and drop PDF files, or click to browse</p>
            <p className="mt-1 text-xs text-muted-foreground">Only .pdf files are supported</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              multiple
              className="hidden"
              onChange={(event) => handleFiles(event.target.files)}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Indexed documents</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="space-y-3 p-4">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : documents.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No documents uploaded yet.</p>
              ) : (
                documents.map((document) => <DocumentRow key={document.id} document={document} />)
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
