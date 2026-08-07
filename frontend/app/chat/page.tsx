"use client";

import { useRef, useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { MessageBubble, type ChatMessage } from "@/components/chat/message-bubble";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { streamAsk } from "@/lib/api";

function newId(): string {
  return crypto.randomUUID();
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  function scrollToBottom() {
    requestAnimationFrame(() => scrollRef.current?.scrollIntoView({ behavior: "smooth" }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const question = input.trim();
    if (!question || isStreaming) return;

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

    await streamAsk(question, {
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
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
              Ask a question about your company documents to get started.
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-6">
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
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
              disabled={isStreaming}
            />
            <Button type="submit" size="icon" disabled={isStreaming || !input.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
