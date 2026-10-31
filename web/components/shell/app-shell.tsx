"use client";

import { LogOut, Plus, Search, Sun, Users, Waypoints, type LucideIcon } from "lucide-react";
import { signOut } from "next-auth/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Logo } from "@/components/brand/logo";
import { AddSave } from "@/components/saves/add-save";

const NAV: { href: string; label: string; Icon: LucideIcon }[] = [
  { href: "/today", label: "Today", Icon: Sun },
  { href: "/threads", label: "Threads", Icon: Waypoints },
  { href: "/search", label: "Ask", Icon: Search },
  { href: "/team", label: "Team", Icon: Users },
];

export function AppShell({ name, children }: { name: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const [adding, setAdding] = useState(false);

  return (
    <div className="min-h-dvh md:flex">
      {/* Desktop: glass sidebar */}
      <aside className="glass sticky top-4 m-4 hidden h-[calc(100dvh-2rem)] w-60 shrink-0 flex-col rounded-[var(--radius-card)] p-5 md:flex">
        <Logo />
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="mt-8 flex items-center justify-center gap-2 rounded-full bg-red px-4 py-2.5 text-sm font-semibold text-white shadow-[0_6px_20px_rgb(210_64_47/0.35)] hover:bg-red-600"
        >
          <Plus className="size-[18px]" strokeWidth={2.2} aria-hidden />
          Add
        </button>
        <nav className="mt-4 flex flex-col gap-1">
          {NAV.map(({ href, label, Icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-full px-4 py-2.5 text-sm font-semibold ${
                isActive(href) ? "bg-ink text-white" : "text-ink-2 hover:bg-glass-strong"
              }`}
            >
              <Icon className="size-[18px]" strokeWidth={1.8} aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto">
          <p className="truncate px-4 text-sm text-muted">{name}</p>
          <button
            type="button"
            onClick={() => signOut({ callbackUrl: "/" })}
            className="mt-2 flex items-center gap-3 rounded-full px-4 py-2.5 text-sm font-semibold text-ink-2 hover:bg-glass-strong"
          >
            <LogOut className="size-[18px]" strokeWidth={1.8} aria-hidden />
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile: top bar with sign-out */}
      <header className="flex items-center justify-between px-5 pt-5 md:hidden">
        <Logo size={24} />
        <button
          type="button"
          onClick={() => signOut({ callbackUrl: "/" })}
          aria-label="Sign out"
          className="glass rounded-full p-2"
        >
          <LogOut className="size-[18px] text-ink-2" strokeWidth={1.8} />
        </button>
      </header>

      <main className="mx-auto w-full max-w-[720px] px-5 pb-28 pt-6 md:pb-10 md:pt-10">
        {children}
      </main>

      {/* Mobile: add button above the tabs */}
      <button
        type="button"
        onClick={() => setAdding(true)}
        aria-label="Add a save"
        className="fixed bottom-24 right-5 z-10 rounded-full bg-red p-4 text-white shadow-[0_8px_24px_rgb(210_64_47/0.4)] md:hidden"
      >
        <Plus className="size-6" strokeWidth={2.2} />
      </button>

      {/* Mobile: glass bottom tabs */}
      <nav className="glass fixed inset-x-4 bottom-4 z-10 flex justify-around rounded-full px-2 py-2 md:hidden">
        {NAV.map(({ href, label, Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex flex-col items-center gap-0.5 rounded-full px-4 py-1.5 text-[11px] font-semibold ${
              isActive(href) ? "bg-ink text-white" : "text-ink-2"
            }`}
          >
            <Icon className="size-[18px]" strokeWidth={1.8} aria-hidden />
            {label}
          </Link>
        ))}
      </nav>

      {adding && <AddSave onClose={() => setAdding(false)} />}
    </div>
  );
}
