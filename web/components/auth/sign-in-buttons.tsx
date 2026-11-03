"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";

export function SignInButtons({ demo, google }: { demo: boolean; google: boolean }) {
  const [pending, setPending] = useState<"demo" | "google" | null>(null);

  const go = (provider: "demo" | "google") => {
    setPending(provider);
    void signIn(provider, { callbackUrl: "/today" });
  };

  return (
    <div className="mt-8">
      <div className="flex flex-wrap justify-center gap-3">
        {demo && (
          <button
            type="button"
            onClick={() => go("demo")}
            disabled={pending !== null}
            className="rounded-full bg-red px-6 py-3 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-70"
          >
            {pending === "demo" ? "Opening the demo…" : "Try the demo"}
          </button>
        )}
        {google && (
          <button
            type="button"
            onClick={() => go("google")}
            disabled={pending !== null}
            className="glass rounded-full px-6 py-3 text-sm font-semibold disabled:opacity-70"
          >
            {pending === "google" ? "Signing in…" : "Sign in with Google"}
          </button>
        )}
      </div>
      {demo && (
        <p className="mx-auto mt-3 max-w-md text-center text-sm text-ink-2">
          The demo is a full pile, shared with other visitors.
          {google && " Sign in with Google to start your own, empty and private."}
        </p>
      )}
    </div>
  );
}
