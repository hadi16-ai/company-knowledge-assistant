"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { MessageSquareText, Send } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { MessageBubble, type ChatMessage } from "@/components/chat/message-bubble";
import { PdfViewerModal, type CitationTarget } from "@/components/chat/pdf-viewer-modal";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/lib/auth-context";
import { ApiError, chatApi, streamAsk, type ConversationTurn, type QueryLogEntry } from "@/lib/api";

function newId(): string {
  return crypto.randomUUID();
}

/** Expands each persisted question/answer row into the two chat bubbles that produced it. */
function toChatMessages(entries: QueryLogEntry[]): ChatMessage[] {
  return entries.flatMap((entry) => [
    { id: `${entry.id}-user`, role: "user" as const, content: entry.query },
    { id: `${entry.id}-assistant`, role: "assistant" as const, content: entry.answer },
  ]);
}

export default function ChatPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeCitation, setActiveCitation] = useState<CitationTarget | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollToBottom() {
    requestAnimationFrame(() => scrollRef.current?.scrollIntoView({ behavior: "smooth" }));
  }

  useEffect(() => {
    // Gate on `user` the same way /knowledge does: AppShell withholds rendering until
    // auth resolves, but this component's own effects still run on mount regardless.
    if (!user) return;
    let cancelled = false;
    chatApi
      .getHistory()
      .then((entries) => {
        if (cancelled) return;
        setMessages(toChatMessages(entries));
        setIsHistoryLoading(false);
        scrollToBottom();
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof ApiError) toast.error(error.message);
        setIsHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || isStreaming || isHistoryLoading) return;

    // Prior completed turns give the assistant short-term memory so
    // follow-ups like "what does that section say?" resolve correctly.
    const history: ConversationTurn[] = messages
      .filter((m) => !m.isStreaming && !m.isError && m.content.trim())
      .map((m) => ({ role: m.role, content: m.content }));

    const userMessage: ChatMessage = { id: newId(), role: "user", content: question };
    const assistantId = newId();
    const assistantMessage: ChatMessage = { id: assistantId, role: "assistant", content: "", isStreaming: true };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsStreaming(true);
    scrollToBottom();

    const updateAssistant = (patch: Partial<ChatMessage>) => {
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)));
    };

    await streamAsk(question, history, {
      onSources: (sources) => updateAssistant({ sources }),
      onToken: (text) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + text } : m))
        );
        scrollToBottom();
      },
      onDone: () => {
        updateAssistant({ isStreaming: false });
        setIsStreaming(false);
      },
      onError: (message) => {
        updateAssistant({ content: message, isStreaming: false, isError: true });
        setIsStreaming(false);
      },
    });
  }

  return (
    <AppShell>
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="border-b px-6 py-4">
          <h1 className="text-lg font-semibold">Ask the knowledge base</h1>
          <p className="text-sm text-muted-foreground">
            Answers are grounded in your organization&apos;s indexed documents, with citations.
          </p>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {isHistoryLoading ? (
            <div className="mx-auto flex max-w-3xl flex-col gap-6">
              <Skeleton className="ml-auto h-10 w-2/3" />
              <Skeleton className="h-20 w-3/4" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                <MessageSquareText className="h-5 w-5" />
              </div>
              Ask a question about your company documents to get started.
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-6">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} onSelectCitation={setActiveCitation} />
              ))}
              <div ref={scrollRef} />
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="border-t px-6 py-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleSubmit(event);
                }
              }}
              placeholder="Ask a question about your company documents…"
              className="min-h-11 flex-1 resize-none"
              rows={1}
              disabled={isStreaming || isHistoryLoading}
            />
            <Button
              type="submit"
              size="icon"
              aria-label="Send message"
              disabled={isStreaming || isHistoryLoading || !input.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </form>
      </div>

      <PdfViewerModal citation={activeCitation} onOpenChange={(open) => !open && setActiveCitation(null)} />
    </AppShell>
  );
}
