import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import type { Record } from "../types";

interface Props {
  local: { request: string; response: string; reqarea: string; reqstatus: string; reqid: string };
  remote: Record;
  onResolve: (action: "discard" | "overwrite") => void;
}

export function ConflictDialog({ local, remote, onResolve }: Props) {
  return (
    <Dialog open onOpenChange={(o) => !o && onResolve("discard")}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>This record changed while you were editing</DialogTitle>
          <DialogDescription>
            Another save (you in another tab, or the build process) updated this record after you
            loaded it. Pick how to resolve.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <ColumnPreview title="Your changes" data={local} />
          <ColumnPreview title="Server now has" data={remote} />
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onResolve("discard")}>
            Discard mine, keep server's
          </Button>
          <Button onClick={() => onResolve("overwrite")}>Overwrite with mine</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ColumnPreview({
  title,
  data,
}: {
  title: string;
  data: { request: string; response: string; reqarea: string; reqstatus: string };
}) {
  return (
    <div className="rounded-md border p-3 text-xs">
      <div className="mb-2 font-semibold">{title}</div>
      <Row label="status">{data.reqstatus}</Row>
      <Row label="area">{data.reqarea}</Row>
      <Row label="request">{truncate(data.request)}</Row>
      <Row label="response">{truncate(data.response)}</Row>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex border-b py-1 last:border-0">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="flex-1 break-words">{children}</span>
    </div>
  );
}

function truncate(s: string, n = 200): string {
  if (!s) return "(empty)";
  return s.length > n ? s.slice(0, n) + "…" : s;
}
