"use client";

import { useState } from "react";
import { Loader2, MessageSquare, Plus, Trash2 } from "lucide-react";
import type { Conversation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

interface ConversationSidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  isLoading: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => Promise<void>;
}

/** Buckets conversations by recency for the sidebar's Today/Yesterday/Older grouping. */
function groupByRecency(conversations: Conversation[]): { label: string; items: Conversation[] }[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 24 * 60 * 60 * 1000);

  const today: Conversation[] = [];
  const yesterday: Conversation[] = [];
  const older: Conversation[] = [];

  for (const conversation of conversations) {
    const updatedAt = new Date(conversation.updated_at);
    if (updatedAt >= startOfToday) today.push(conversation);
    else if (updatedAt >= startOfYesterday) yesterday.push(conversation);
    else older.push(conversation);
  }

  return [
    { label: "Today", items: today },
    { label: "Yesterday", items: yesterday },
    { label: "Older", items: older },
  ].filter((group) => group.items.length > 0);
}

export function ConversationSidebar({
  conversations,
  activeId,
  isLoading,
  onSelect,
  onNew,
  onDelete,
}: ConversationSidebarProps) {
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const pendingDelete = conversations.find((c) => c.id === pendingDeleteId) ?? null;

  async function handleConfirmDelete() {
    if (!pendingDeleteId) return;
    setIsDeleting(true);
    try {
      await onDelete(pendingDeleteId);
      setPendingDeleteId(null);
    } finally {
      setIsDeleting(false);
    }
  }

  const groups = groupByRecency(conversations);

  return (
    <div className="flex w-64 shrink-0 flex-col border-r">
      <div className="shrink-0 border-b p-3">
        <Button variant="outline" className="w-full justify-start" onClick={onNew}>
          <Plus className="h-4 w-4" />
          New conversation
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-3 py-8 text-center text-xs text-muted-foreground">
            <MessageSquare className="h-5 w-5" />
            No conversations yet.
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-3">
              <p className="px-2 py-1 text-xs font-medium text-muted-foreground">{group.label}</p>
              {group.items.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`group/row flex items-center gap-1 rounded-md px-2 py-1.5 text-sm ${
                    conversation.id === activeId ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    className="min-w-0 flex-1 truncate text-left"
                  >
                    {conversation.title ?? "New conversation"}
                  </button>
                  <button
                    type="button"
                    aria-label="Delete conversation"
                    onClick={() => setPendingDeleteId(conversation.id)}
                    className={`shrink-0 rounded p-1 opacity-0 group-hover/row:opacity-100 ${
                      conversation.id === activeId
                        ? "hover:bg-primary-foreground/20"
                        : "text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    }`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete &quot;{pendingDelete?.title ?? "New conversation"}&quot;?</DialogTitle>
            <DialogDescription>
              This removes the conversation and its messages. This can&apos;t be undone. Your knowledge-base
              documents are not affected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDeleteId(null)} disabled={isDeleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={isDeleting}>
              {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
