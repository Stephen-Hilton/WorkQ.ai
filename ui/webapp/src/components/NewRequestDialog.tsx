import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
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
import { useConfig } from "../config/ConfigContext";
import { api } from "../api/client";
import { USER_SAVE_ACTIONS, type Status } from "../types";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

export function NewRequestDialog({ onClose, onCreated }: Props) {
  const config = useConfig();
  const [request, setRequest] = useState("");
  const [reqarea, setReqarea] = useState("General");
  const [saveAction, setSaveAction] = useState<Status>("pending review");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    if (!request.trim()) {
      setError("request text is required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.create({ request, reqarea, reqstatus: saveAction });
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Request</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
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
            <Label>request</Label>
            <MarkdownEditor value={request} onChange={setRequest} preview="edit" height={300} />
          </div>
          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>
          )}
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <div className="flex items-center gap-1">
            <Button onClick={() => void create()} disabled={busy}>
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
