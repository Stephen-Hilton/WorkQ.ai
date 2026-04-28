import { useEffect, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "./ui/button";
import { Label } from "./ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { MarkdownEditor } from "./MarkdownEditor";
import { ConflictDialog } from "./ConflictDialog";
import { api, ConflictError } from "../api/client";
import { useConfig } from "../config/ConfigContext";
import { formatTimestamp } from "../lib/utils";
import { ALL_STATUSES, USER_SAVE_ACTIONS, type Record, type Status } from "../types";

interface Props {
  record: Record;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (r: Record) => void;
}

export function RequestDetail({ record, onDirtyChange, onSaved }: Props) {
  const config = useConfig();

  const [request, setRequest] = useState(record.request);
  const [response, setResponse] = useState(record.response);
  const [reqarea, setReqarea] = useState(record.reqarea || "General");
  const [reqstatus, setReqstatus] = useState<string>(record.reqstatus);
  const [saveAction, setSaveAction] = useState<Status>("pending review");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<Record | null>(null);

  // Reset local state when the parent passes in a fresh record.
  useEffect(() => {
    setRequest(record.request);
    setResponse(record.response);
    setReqarea(record.reqarea || "General");
    setReqstatus(record.reqstatus);
  }, [record]);

  const dirty = useMemo(
    () =>
      request !== record.request ||
      response !== record.response ||
      reqarea !== (record.reqarea || "General") ||
      reqstatus !== record.reqstatus,
    [request, response, reqarea, reqstatus, record],
  );

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const cancel = () => {
    setRequest(record.request);
    setResponse(record.response);
    setReqarea(record.reqarea || "General");
    setReqstatus(record.reqstatus);
    setError(null);
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.update(record.reqid, {
        request,
        response,
        reqarea,
        reqstatus: saveAction,
        expected_timelog_len: record.timelog?.length ?? 0,
      });
      onSaved(updated);
    } catch (e) {
      if (e instanceof ConflictError) {
        setConflict(e.current);
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const onConflictResolve = (action: "discard" | "overwrite") => {
    if (!conflict) return;
    if (action === "discard") {
      setRequest(conflict.request);
      setResponse(conflict.response);
      setReqarea(conflict.reqarea || "General");
      setReqstatus(conflict.reqstatus);
      setConflict(null);
      onSaved(conflict);
    } else {
      // Overwrite: retry save with the conflict's timelog length so the next
      // attempt is consistent with what's currently on the server.
      void (async () => {
        try {
          setBusy(true);
          const updated = await api.update(record.reqid, {
            request,
            response,
            reqarea,
            reqstatus: saveAction,
            expected_timelog_len: conflict.timelog?.length ?? 0,
          });
          setConflict(null);
          onSaved(updated);
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
        } finally {
          setBusy(false);
        }
      })();
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs sm:grid-cols-4">
        <Field label="reqid" value={record.reqid} mono />
        <Field label="reqcreator" value={record.reqcreator} />
        <Field
          label="created"
          value={formatTimestamp(record.timelog?.[0]?.ts ?? "", config.display_timezone)}
        />
        <Field
          label="reqpr"
          value={
            record.reqpr ? (
              <a
                href={record.reqpr}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center text-primary hover:underline"
              >
                PR <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            ) : (
              <em className="text-muted-foreground">none</em>
            )
          }
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>reqarea</Label>
          <Select value={reqarea} onValueChange={setReqarea}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {config.prompt_areas.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>current reqstatus</Label>
          <Select value={reqstatus} onValueChange={setReqstatus}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ALL_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label>request</Label>
        <MarkdownEditor value={request} onChange={setRequest} preview="edit" height={300} />
      </div>

      <div className="space-y-2">
        <Label>response</Label>
        <MarkdownEditor value={response} onChange={setResponse} preview="live" height={300} />
      </div>

      <details>
        <summary className="cursor-pointer text-sm font-medium">timelog ({record.timelog?.length ?? 0})</summary>
        <ul className="mt-2 space-y-1 text-xs font-mono">
          {(record.timelog ?? []).map((e, i) => (
            <li key={i} className="flex justify-between border-b border-dashed py-1">
              <span>{e.status}</span>
              <span className="text-muted-foreground">
                {formatTimestamp(e.ts, config.display_timezone)}
              </span>
            </li>
          ))}
        </ul>
      </details>

      {error && <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}

      <div className="flex flex-col gap-2 border-t pt-3 sm:flex-row sm:items-center sm:justify-end">
        <Button variant="outline" onClick={cancel} disabled={!dirty || busy}>
          Cancel
        </Button>
        <div className="flex items-center gap-1">
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : "Save and"}
          </Button>
          <Select value={saveAction} onValueChange={(v) => setSaveAction(v as Status)}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {USER_SAVE_ACTIONS.map((s) => (
                <SelectItem key={s} value={s}>
                  {s === "queued for build"
                    ? "Queue for Build"
                    : s === "queued for planning"
                    ? "Queue for Planning"
                    : s === "pending review"
                    ? "Mark for Review"
                    : "Complete"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {conflict && (
        <ConflictDialog
          local={{ request, response, reqarea, reqstatus, reqid: record.reqid }}
          remote={conflict}
          onResolve={onConflictResolve}
        />
      )}
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`truncate ${mono ? "font-mono" : ""}`}>{value || <em className="text-muted-foreground">—</em>}</div>
    </div>
  );
}
