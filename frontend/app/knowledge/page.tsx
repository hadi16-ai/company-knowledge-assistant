"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldAlert, UploadCloud } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { DocumentRow } from "@/components/knowledge/document-row";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth-context";
import { hasAtLeast } from "@/lib/roles";
import { ApiError, documentsApi, type DocumentRecord } from "@/lib/api";

const POLL_INTERVAL_MS = 4000;

export default function KnowledgePage() {
  const { user } = useAuth();
  // Upload/replace/reindex need Manager+; delete is stricter, Company Admin+ only.
  const canManage = hasAtLeast(user?.role, "manager");
  const canDelete = hasAtLeast(user?.role, "admin");
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
    // AppShell withholds rendering until `user` resolves, but this component's own
    // effects still run on mount regardless — gate on `user` so this doesn't fire an
    // authenticated request (and surface a spurious "Not authenticated" toast) before
    // the auth check has settled.
    if (!user) return;
    // Deferred via microtask so no setState call happens synchronously within the effect body.
    void Promise.resolve().then(refreshDocuments);
  }, [user, refreshDocuments]);

  useEffect(() => {
    if (!user) return;
    const hasInFlight = documents.some((d) => d.status === "pending" || d.status === "processing");
    if (!hasInFlight) return;
    const interval = setInterval(refreshDocuments, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [user, documents, refreshDocuments]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error(`${file.name} is not a PDF file.`);
        continue;
      }
      try {
        const accepted = await documentsApi.upload(file);
        toast.success(`${accepted.filename} queued for processing.`);
        await refreshDocuments();
      } catch (error) {
        toast.error(error instanceof ApiError ? error.message : `Failed to upload ${file.name}.`);
      }
    }
  }

  async function handleView(document: DocumentRecord) {
    try {
      const { url } = await documentsApi.getViewUrl(document.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to open document.");
    }
  }

  async function handleReplace(document: DocumentRecord, file: File) {
    try {
      await documentsApi.replace(document.id, file);
      toast.success(`${file.name} queued to replace "${document.filename}".`);
      await refreshDocuments();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to replace document.");
    }
  }

  async function handleReindex(document: DocumentRecord) {
    try {
      await documentsApi.reindex(document.id);
      toast.success(`"${document.filename}" queued for re-indexing.`);
      await refreshDocuments();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to re-index document.");
    }
  }

  async function handleDelete(document: DocumentRecord) {
    try {
      await documentsApi.delete(document.id);
      toast.success(`"${document.filename}" deleted.`);
      setDocuments((prev) => prev.filter((d) => d.id !== document.id));
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to delete document.");
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
          {canManage ? (
            <div
              role="button"
              tabIndex={0}
              aria-label="Upload PDF files"
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
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors focus-visible:border-ring focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
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
          ) : (
            <div className="flex items-center gap-3 rounded-lg border border-dashed px-6 py-4 text-sm text-muted-foreground">
              <ShieldAlert className="h-4 w-4 shrink-0" />
              Only managers and admins can upload or replace documents. Ask an admin in your organization for changes.
            </div>
          )}

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
                documents.map((document) => (
                  <DocumentRow
                    key={document.id}
                    document={document}
                    canManage={canManage}
                    canDelete={canDelete}
                    onView={handleView}
                    onReplace={handleReplace}
                    onReindex={handleReindex}
                    onDelete={handleDelete}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
