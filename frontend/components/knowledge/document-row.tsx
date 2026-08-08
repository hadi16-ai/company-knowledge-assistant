"use client";

import { useRef, useState } from "react";
import {
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  MoreVertical,
  RefreshCw,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import type { DocumentRecord } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const STATUS_CONFIG: Record<DocumentRecord["status"], { label: string; icon: React.ElementType; className: string }> = {
  pending: { label: "Queued", icon: Clock, className: "text-muted-foreground" },
  processing: { label: "Processing", icon: Loader2, className: "text-blue-600" },
  ready: { label: "Ready", icon: CheckCircle2, className: "text-emerald-600" },
  failed: { label: "Failed", icon: XCircle, className: "text-destructive" },
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface DocumentRowProps {
  document: DocumentRecord;
  /** Manager+: can upload/replace/reindex. */
  canManage: boolean;
  /** Company Admin+: can delete. Always true when `canManage` would need it disabled. */
  canDelete: boolean;
  onView: (document: DocumentRecord) => void;
  onReplace: (document: DocumentRecord, file: File) => Promise<void>;
  onReindex: (document: DocumentRecord) => Promise<void>;
  onDelete: (document: DocumentRecord) => Promise<void>;
}

export function DocumentRow({ document, canManage, canDelete, onView, onReplace, onReindex, onDelete }: DocumentRowProps) {
  const status = STATUS_CONFIG[document.status];
  const StatusIcon = status.icon;
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const isInFlight = document.status === "pending" || document.status === "processing";

  async function handleReindex() {
    setIsBusy(true);
    try {
      await onReindex(document);
    } finally {
      setIsBusy(false);
    }
  }

  async function handleReplaceFile(file: File | undefined) {
    if (!file) return;
    setIsBusy(true);
    try {
      await onReplace(document, file);
    } finally {
      setIsBusy(false);
    }
  }

  async function handleConfirmDelete() {
    setIsBusy(true);
    try {
      await onDelete(document);
      setIsDeleteOpen(false);
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0">
      <button
        type="button"
        onClick={() => onView(document)}
        disabled={document.status !== "ready"}
        className="flex min-w-0 flex-1 items-center gap-3 text-left disabled:cursor-default"
      >
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium hover:underline">{document.filename}</p>
          <p className="text-xs text-muted-foreground">
            {formatBytes(document.size_bytes)}
            {document.status === "ready" &&
              ` · ${document.chunk_count} chunks${document.page_count ? ` · ${document.page_count} pages` : ""}`}
            {document.status === "failed" && document.error_message && ` · ${document.error_message}`}
          </p>
        </div>
      </button>

      <Badge variant="outline" className={`shrink-0 gap-1 ${status.className}`}>
        <StatusIcon className={`h-3 w-3 ${document.status === "processing" ? "animate-spin" : ""}`} />
        {status.label}
      </Badge>

      {canManage && (
        <DropdownMenu>
          <DropdownMenuTrigger
            disabled={isBusy}
            aria-label={`Actions for ${document.filename}`}
            className={buttonVariants({ variant: "ghost", size: "icon", className: "shrink-0 text-muted-foreground" })}
          >
            {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MoreVertical className="h-4 w-4" />}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem disabled={isInFlight} onClick={handleReindex}>
              <RefreshCw className="h-4 w-4" />
              Re-index
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => replaceInputRef.current?.click()}>
              <Upload className="h-4 w-4" />
              Replace file
            </DropdownMenuItem>
            {canDelete && (
              <DropdownMenuItem variant="destructive" onClick={() => setIsDeleteOpen(true)}>
                <Trash2 className="h-4 w-4" />
                Delete
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <input
        ref={replaceInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(event) => {
          void handleReplaceFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />

      <Dialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete &quot;{document.filename}&quot;?</DialogTitle>
            <DialogDescription>
              This removes the file, its indexed chunks, and its ingestion history. This can&apos;t be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDeleteOpen(false)} disabled={isBusy}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={isBusy}>
              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
