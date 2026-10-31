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
    <div className="mt-8 flex flex-wrap justify-center gap-3">
      {demo && (
        <button
          type="button"
          onClick={() => go("demo")}
          disabled={pending !== null}
          className="rounded-full bg-red px-6 py-3 text-sm font-semibold text-white shadow-[0_6px_20px_rgb(210_64_47/0.35)] hover:bg-red-600 disabled:opacity-70"
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
  );
}
