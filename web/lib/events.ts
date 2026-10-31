"use client";

import { useEffect, useRef, useState } from "react";

import { type AgentEvent, toAgentEvent } from "@/lib/api";

export type StreamStatus = "connecting" | "live" | "reconnecting";

/**
 * Subscribes to the live team feed. EventSource reconnects by itself and sends
 * Last-Event-ID, so the server resumes where we left off (docs/07-api.md).
 */
export function useEventStream(onEvent: (event: AgentEvent) => void): StreamStatus {
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const handler = useRef(onEvent);

  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const source = new EventSource("/api/stream");
    // The server ends each stream after a minute and we reconnect within seconds;
    // only call it "reconnecting" if that takes longer.
    let grace: ReturnType<typeof setTimeout> | undefined;
    source.onopen = () => {
      clearTimeout(grace);
      setStatus("live");
    };
    source.onerror = () => {
      clearTimeout(grace);
      grace = setTimeout(() => setStatus("reconnecting"), 4000);
    };
    source.addEventListener("agent_event", (e) => {
      handler.current(toAgentEvent(JSON.parse((e as MessageEvent<string>).data)));
    });
    return () => {
      clearTimeout(grace);
      source.close();
    };
  }, []);

  return status;
}
