"use client";

import { useEffect, useRef } from "react";

type LiveRefreshOptions = {
  enabled?: boolean;
  intervalMs?: number;
  onError?: (error: unknown) => void;
};

export function useLiveRefresh(refresh: () => Promise<void> | void, options: LiveRefreshOptions = {}) {
  const { enabled = true, intervalMs = 3000, onError } = options;
  const refreshRef = useRef(refresh);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    refreshRef.current = refresh;
  }, [refresh]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let inFlight = false;

    async function runRefresh() {
      if (inFlight || document.visibilityState === "hidden") {
        return;
      }

      inFlight = true;
      try {
        await refreshRef.current();
      } catch (error) {
        onErrorRef.current?.(error);
      } finally {
        inFlight = false;
      }
    }

    const intervalId = window.setInterval(runRefresh, intervalMs);

    function refreshWhenVisible() {
      if (document.visibilityState === "visible") {
        void runRefresh();
      }
    }

    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("focus", refreshWhenVisible);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("focus", refreshWhenVisible);
    };
  }, [enabled, intervalMs]);
}
