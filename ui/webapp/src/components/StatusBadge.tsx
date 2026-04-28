import { Badge } from "./ui/badge";

const VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  "queued for build": "secondary",
  "queued for planning": "secondary",
  "pending review": "outline",
  building: "default",
  planning: "default",
  complete: "default",
  failed: "destructive",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={VARIANT[status] ?? "outline"}>{status}</Badge>;
}
