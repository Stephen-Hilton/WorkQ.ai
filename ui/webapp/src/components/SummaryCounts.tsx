import { Badge } from "./ui/badge";
import { ALL_STATUSES, type Record } from "../types";

interface Props {
  records: Record[];
}

export function SummaryCounts({ records }: Props) {
  const counts = ALL_STATUSES.reduce<Map<string, number>>((m, s) => {
    m.set(s, 0);
    return m;
  }, new Map());
  for (const r of records) {
    counts.set(r.reqstatus, (counts.get(r.reqstatus) ?? 0) + 1);
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="default">Total: {records.length}</Badge>
      {ALL_STATUSES.map((s) => {
        const n = counts.get(s) ?? 0;
        if (n === 0) return null;
        return (
          <Badge key={s} variant="secondary" className="font-normal">
            {s}: {n}
          </Badge>
        );
      })}
    </div>
  );
}
