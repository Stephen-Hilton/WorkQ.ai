import { useState } from "react";
import { MoreVertical } from "lucide-react";
import {
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "./ui/accordion";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Button } from "./ui/button";
import { StatusBadge } from "./StatusBadge";
import { RequestDetail } from "./RequestDetail";
import { api } from "../api/client";
import { firstLine, formatTimestamp } from "../lib/utils";
import { useConfig } from "../config/ConfigContext";
import type { Record, Status } from "../types";
import { USER_SAVE_ACTIONS } from "../types";

interface Props {
  record: Record;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (r: Record) => void;
  onDeleted: (reqid: string) => void;
}

export function RequestRow({ record, onDirtyChange, onSaved, onDeleted }: Props) {
  const config = useConfig();
  const [busy, setBusy] = useState(false);
  const created = record.timelog?.[0]?.ts ?? "";

  const transitionStatus = async (status: Status) => {
    setBusy(true);
    try {
      const updated = await api.update(record.reqid, {
        reqstatus: status,
        expected_timelog_len: record.timelog?.length ?? 0,
      });
      onSaved(updated);
    } catch (e) {
      alert(`Could not change status: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const cloneRequest = async () => {
    setBusy(true);
    try {
      const newRequest =
        record.response && record.response.trim()
          ? `${record.request}\n\n## Previous AI Response\n\n${record.response}`
          : record.request;
      const created = await api.create({
        request: newRequest,
        reqarea: record.reqarea,
        reqstatus: "pending review",
      });
      // Refresh-via-onSaved sentinel.
      onSaved(created);
    } catch (e) {
      alert(`Could not clone: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const deleteRequest = async () => {
    if (!confirm("Delete this request? This cannot be undone.")) return;
    setBusy(true);
    try {
      await api.remove(record.reqid);
      onDeleted(record.reqid);
    } catch (e) {
      alert(`Could not delete: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AccordionItem value={record.reqid}>
      <div className="flex items-center justify-between gap-2 pr-2">
        <div className="flex-1 min-w-0">
          <AccordionTrigger>
            <div className="flex flex-wrap items-center gap-2 text-left">
              <StatusBadge status={record.reqstatus} />
              <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
                {record.reqarea || "General"}
              </span>
              <span className="truncate text-sm font-medium">
                {firstLine(record.request) || <em className="text-muted-foreground">(empty request)</em>}
              </span>
              <span className="text-xs text-muted-foreground">
                {formatTimestamp(created, config.display_timezone)}
              </span>
            </div>
          </AccordionTrigger>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" disabled={busy} title="Actions">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Status</DropdownMenuLabel>
            {USER_SAVE_ACTIONS.map((s) => (
              <DropdownMenuItem key={s} onClick={() => transitionStatus(s)}>
                {s === "queued for build"
                  ? "Queue for Build"
                  : s === "queued for planning"
                  ? "Queue for Planning"
                  : s === "pending review"
                  ? "Mark for Review"
                  : "Complete"}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Record</DropdownMenuLabel>
            <DropdownMenuItem onClick={() => void cloneRequest()}>
              Clone this Request
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => void deleteRequest()}
              className="text-destructive focus:text-destructive"
            >
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <AccordionContent>
        <RequestDetail
          record={record}
          onDirtyChange={onDirtyChange}
          onSaved={onSaved}
        />
      </AccordionContent>
    </AccordionItem>
  );
}
