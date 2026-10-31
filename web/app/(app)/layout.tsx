import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { Providers } from "@/components/providers";
import { AppShell } from "@/components/shell/app-shell";
import { authOptions } from "@/lib/auth";

/**
 * Everything inside (app) needs a signed-in user. With Cache Components, reading the
 * session is request-time work, so it sits behind a Suspense boundary.
 */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-dvh" aria-busy />}>
      <SignedIn>{children}</SignedIn>
    </Suspense>
  );
}

async function SignedIn({ children }: { children: React.ReactNode }) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) redirect("/");

  return (
    <Providers>
      <AppShell name={session.user.name ?? session.user.email ?? "You"}>{children}</AppShell>
    </Providers>
  );
}
