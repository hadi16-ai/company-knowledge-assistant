import { FileText } from "lucide-react";
import type { SourceCitation } from "@/lib/api";
import type { CitationTarget } from "@/components/chat/pdf-viewer-modal";
import { Badge } from "@/components/ui/badge";

interface FilenameGroup {
  documentId: string | null;
  pages: Map<number | null, number>;
}

export function SourceCitations({
  sources,
  onSelectCitation,
}: {
  sources: SourceCitation[];
  onSelectCitation: (target: CitationTarget) => void;
}) {
  if (sources.length === 0) return null;

  const grouped = new Map<string, FilenameGroup>();
  for (const source of sources) {
    const group = grouped.get(source.filename) ?? { documentId: source.document_id, pages: new Map() };
    group.pages.set(source.page_number, Math.max(group.pages.get(source.page_number) ?? 0, source.score));
    grouped.set(source.filename, group);
  }

  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      <div className="flex flex-wrap gap-2">
        {Array.from(grouped.entries()).map(([filename, { documentId, pages }]) => (
          <div key={filename} className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
            <div className="mb-1 flex items-center gap-1.5 font-medium">
              <FileText className="h-3.5 w-3.5" />
              {filename}
            </div>
            <div className="flex flex-wrap gap-1">
              {Array.from(pages.entries()).map(([page, score]) => {
                const clickable = Boolean(documentId);
                return (
                  <Badge
                    key={String(page)}
                    variant="outline"
                    className={clickable ? "font-normal cursor-pointer hover:bg-muted" : "font-normal"}
                    render={
                      clickable ? (
                        <button
                          type="button"
                          onClick={() => onSelectCitation({ documentId: documentId!, filename, pageNumber: page })}
                        />
                      ) : undefined
                    }
                  >
                    {page ? `Page ${page}` : "Page n/a"} · {Math.round(score * 100)}%
                  </Badge>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
