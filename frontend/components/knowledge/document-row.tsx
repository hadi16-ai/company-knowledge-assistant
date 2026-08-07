import { CheckCircle2, Clock, FileText, Loader2, XCircle } from "lucide-react";
import type { DocumentRecord } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

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

export function DocumentRow({ document }: { document: DocumentRecord }) {
  const status = STATUS_CONFIG[document.status];
  const StatusIcon = status.icon;

  return (
    <div className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0">
      <div className="flex min-w-0 items-center gap-3">
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{document.filename}</p>
          <p className="text-xs text-muted-foreground">
            {formatBytes(document.size_bytes)}
            {document.status === "ready" && ` · ${document.chunk_count} chunks`}
            {document.status === "failed" && document.error_message && ` · ${document.error_message}`}
          </p>
        </div>
      </div>
      <Badge variant="outline" className={`shrink-0 gap-1 ${status.className}`}>
        <StatusIcon className={`h-3 w-3 ${document.status === "processing" ? "animate-spin" : ""}`} />
        {status.label}
      </Badge>
    </div>
  );
}
