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
    source.onopen = () => setStatus("live");
    source.onerror = () => setStatus("reconnecting");
    source.addEventListener("agent_event", (e) => {
      handler.current(toAgentEvent(JSON.parse((e as MessageEvent<string>).data)));
    });
    return () => source.close();
  }, []);

  return status;
}
