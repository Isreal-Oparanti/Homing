"use client";

import { useEffect, useRef, useState } from "react";

import { type AgentEvent, toAgentEvent } from "@/lib/api";

export type StreamStatus = "connecting" | "live" | "reconnecting";

type Listener = (event: AgentEvent) => void;

// One live connection per tab, shared by every component that listens: a page with several
// live parts (Today, Found for you, the shell) still opens a single stream.
const listeners = new Set<Listener>();
const watchers = new Set<(status: StreamStatus) => void>();
let source: EventSource | null = null;
let status: StreamStatus = "connecting";
let grace: ReturnType<typeof setTimeout> | undefined;

function announce(next: StreamStatus) {
  status = next;
  watchers.forEach((watch) => watch(next));
}

function open() {
  source = new EventSource("/api/stream");
  // The server ends each stream after a minute and we reconnect within seconds;
  // only call it "reconnecting" if that takes longer.
  source.onopen = () => {
    clearTimeout(grace);
    announce("live");
  };
  source.onerror = () => {
    clearTimeout(grace);
    grace = setTimeout(() => announce("reconnecting"), 4000);
  };
  source.addEventListener("agent_event", (e) => {
    const event = toAgentEvent(JSON.parse((e as MessageEvent<string>).data));
    listeners.forEach((listen) => listen(event));
  });
}

function close() {
  clearTimeout(grace);
  source?.close();
  source = null;
  status = "connecting";
}

/**
 * Subscribes to the live team feed. EventSource reconnects by itself and sends
 * Last-Event-ID, so the server resumes where we left off (docs/07-api.md).
 */
export function useEventStream(onEvent: (event: AgentEvent) => void): StreamStatus {
  const [current, setCurrent] = useState<StreamStatus>(status);
  const handler = useRef(onEvent);

  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    const listen: Listener = (event) => handler.current(event);
    listeners.add(listen);
    watchers.add(setCurrent);
    if (source === null) open();
    return () => {
      listeners.delete(listen);
      watchers.delete(setCurrent);
      if (listeners.size === 0) close();
    };
  }, []);

  return current;
}
