import { Bot, User } from "lucide-react";
import { SourceCitations } from "@/components/chat/source-citations";
import type { CitationTarget } from "@/components/chat/pdf-viewer-modal";
import type { SourceCitation } from "@/lib/api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
  isStreaming?: boolean;
  isError?: boolean;
}

export function MessageBubble({
  message,
  onSelectCitation,
}: {
  message: ChatMessage;
  onSelectCitation: (target: CitationTarget) => void;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`max-w-2xl rounded-lg border px-4 py-3 text-base ${
          isUser ? "bg-primary text-primary-foreground" : message.isError ? "border-destructive/50 bg-destructive/10" : "bg-card"
        }`}
      >
        <p className="whitespace-pre-wrap leading-relaxed">
          {message.content}
          {message.isStreaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-current align-middle" />}
        </p>
        {!isUser && message.sources && (
          <SourceCitations sources={message.sources} onSelectCitation={onSelectCitation} />
        )}
      </div>
    </div>
  );
}
