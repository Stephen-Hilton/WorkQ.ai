import { useEffect, useRef, useState } from "react";

const REFRESH_MS = 20_000;

export function useAutoRefresh(refresh: () => void | Promise<void>, paused: boolean) {
  const [tickCount, setTickCount] = useState(0);
  const cb = useRef(refresh);
  cb.current = refresh;

  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => {
      setTickCount((t) => t + 1);
      void cb.current();
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [paused]);

  return { tickCount };
}
