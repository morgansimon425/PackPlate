"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "./api";

interface Settled<T> {
  key: string;
  nonce: number;
  data?: T;
  error?: string;
}

// Runs `load` whenever `key` changes and returns what it produced. `loading`
// is derived (nothing has settled for the current key yet) rather than set, so
// there is never a stale spinner or a state update inside the effect body.
export function useAsync<T>(
  load: () => Promise<T>,
  key: string,
  { keepDataOnError = false } = {},
) {
  const loadRef = useRef(load);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let cancelled = false;
    loadRef
      .current()
      .then((data) => {
        if (!cancelled) setSettled({ key, nonce, data });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setSettled((previous) => ({
            key,
            nonce,
            error: errorMessage(error),
            data:
              keepDataOnError && previous?.key === key
                ? previous.data
                : undefined,
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [key, nonce, keepDataOnError]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const forThisKey = settled !== null && settled.key === key ? settled : null;
  return {
    data: forThisKey?.data,
    error: forThisKey?.error,
    loading: !(forThisKey !== null && forThisKey.nonce === nonce),
    reload,
  };
}
