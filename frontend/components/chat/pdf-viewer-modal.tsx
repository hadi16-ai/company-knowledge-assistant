"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, documentsApi } from "@/lib/api";

export interface CitationTarget {
  documentId: string;
  filename: string;
  pageNumber: number | null;
}

export function PdfViewerModal({
  citation,
  onOpenChange,
}: {
  citation: CitationTarget | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [viewUrl, setViewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Deferred via microtask so no setState call happens synchronously within the effect body.
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setViewUrl(null);
      setError(null);
    });

    if (citation) {
      documentsApi
        .getViewUrl(citation.documentId)
        .then(({ url }) => {
          if (!cancelled) setViewUrl(url);
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load document.");
        });
    }

    return () => {
      cancelled = true;
    };
  }, [citation]);

  const iframeSrc = viewUrl && citation?.pageNumber ? `${viewUrl}#page=${citation.pageNumber}` : viewUrl;

  return (
    <Dialog open={citation !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] w-[90vw] max-w-4xl flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="truncate pr-6">
            {citation?.filename}
            {citation?.pageNumber ? ` · Page ${citation.pageNumber}` : ""}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-hidden rounded-md border bg-muted/20">
          {error ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-destructive">
              {error}
            </div>
          ) : iframeSrc ? (
            <iframe src={iframeSrc} title={citation?.filename ?? "Document preview"} className="h-full w-full" />
          ) : (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
