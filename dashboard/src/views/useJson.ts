import { useEffect, useState } from "react";

export type Loadable<T> = { state: "loading" } | { state: "error" } | { state: "empty" } | { state: "ready"; data: T };

export function useJson<T>(url: string, isEmpty: (data: T) => boolean): Loadable<T> {
  const [result, setResult] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then((r) => (r.status === 404 ? null : r.ok ? (r.json() as Promise<T>) : Promise.reject(new Error(String(r.status)))))
      .then((data) => setResult(data === null || isEmpty(data) ? { state: "empty" } : { state: "ready", data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setResult({ state: "error" });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);
  return result;
}
