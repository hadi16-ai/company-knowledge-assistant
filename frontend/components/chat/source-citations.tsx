import { FileText } from "lucide-react";
import type { SourceCitation } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export function SourceCitations({ sources }: { sources: SourceCitation[] }) {
  if (sources.length === 0) return null;

  const grouped = new Map<string, Map<number | null, number>>();
  for (const source of sources) {
    const pages = grouped.get(source.filename) ?? new Map<number | null, number>();
    pages.set(source.page_number, Math.max(pages.get(source.page_number) ?? 0, source.score));
    grouped.set(source.filename, pages);
  }

  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      <div className="flex flex-wrap gap-2">
        {Array.from(grouped.entries()).map(([filename, pages]) => (
          <div key={filename} className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
            <div className="mb-1 flex items-center gap-1.5 font-medium">
              <FileText className="h-3.5 w-3.5" />
              {filename}
            </div>
            <div className="flex flex-wrap gap-1">
              {Array.from(pages.entries()).map(([page, score]) => (
                <Badge key={String(page)} variant="outline" className="font-normal">
                  {page ? `Page ${page}` : "Page n/a"} · {Math.round(score * 100)}%
                </Badge>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
