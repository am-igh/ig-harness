import { useCallback, useEffect, useRef, useState } from "react";
import { type Item, type Revealed, reveal } from "../api";

/** Details of a masked (personal) item, fetched only when she clicks, and hidden again after a minute. */
export function useReveal(it: Pick<Item, "type" | "id" | "masked">) {
  const [shown, setShown] = useState<Revealed | null>(null);
  const timer = useRef<number>();
  const hide = useCallback(() => { window.clearTimeout(timer.current); setShown(null); }, []);
  const show = useCallback(async () => {
    const r = await reveal(it);
    setShown(r);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(null), 60_000);
    return r;
  }, [it.type, it.id]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return { shown: it.masked ? shown : null, show, hide };
}
