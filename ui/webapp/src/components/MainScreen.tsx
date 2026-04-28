import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Plus, LogOut } from "lucide-react";
import { Button } from "./ui/button";
import { Accordion } from "./ui/accordion";
import { SummaryCounts } from "./SummaryCounts";
import { RequestRow } from "./RequestRow";
import { NewRequestDialog } from "./NewRequestDialog";
import { useAuth } from "../auth/AuthContext";
import { useAutoRefresh } from "../hooks/useAutoRefresh";
import { api } from "../api/client";
import type { Record } from "../types";

export function MainScreen() {
  const { email, signOut } = useAuth();
  const [records, setRecords] = useState<Record[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  // Set of reqids whose accordion is expanded AND has unsaved edits.
  const [editingDirty, setEditingDirty] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const resp = await api.listAll();
      // Sort newest first by first timelog entry (creation time).
      const sorted = [...resp.items].sort((a, b) => {
        const aTs = a.timelog?.[0]?.ts ?? "";
        const bTs = b.timelog?.[0]?.ts ?? "";
        return bTs.localeCompare(aTs);
      });
      setRecords(sorted);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  const paused = editingDirty.size > 0;
  useAutoRefresh(refresh, paused);

  const setDirty = useCallback((reqid: string, dirty: boolean) => {
    setEditingDirty((prev) => {
      const next = new Set(prev);
      if (dirty) next.add(reqid);
      else next.delete(reqid);
      return next;
    });
  }, []);

  const onSaved = useCallback(
    (updated: Record) => {
      setDirty(updated.reqid, false);
      void refresh();
    },
    [refresh, setDirty],
  );

  const onDeleted = useCallback(
    (reqid: string) => {
      setDirty(reqid, false);
      void refresh();
    },
    [refresh, setDirty],
  );

  const summary = useMemo(() => <SummaryCounts records={records} />, [records]);

  return (
    <div className="container mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">WorkQ.ai</h1>
          <p className="text-xs text-muted-foreground">{email}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setShowNew(true)} size="sm">
            <Plus className="mr-1 h-4 w-4" /> New Request
          </Button>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            <RefreshCw className="mr-1 h-4 w-4" /> Refresh
          </Button>
          <Button variant="ghost" size="sm" onClick={signOut} title="Sign out">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <div className="mb-6">{summary}</div>

      {paused && (
        <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Auto-refresh paused while editing. Save or cancel to resume.
        </div>
      )}

      {error && (
        <div className="mb-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : records.length === 0 ? (
        <p className="text-muted-foreground">
          No requests yet. Click <strong>New Request</strong> to create one.
        </p>
      ) : (
        <Accordion type="multiple" className="w-full">
          {records.map((r) => (
            <RequestRow
              key={r.reqid}
              record={r}
              onDirtyChange={(d) => setDirty(r.reqid, d)}
              onSaved={onSaved}
              onDeleted={onDeleted}
            />
          ))}
        </Accordion>
      )}

      {showNew && (
        <NewRequestDialog
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            void refresh();
          }}
        />
      )}
    </div>
  );
}
