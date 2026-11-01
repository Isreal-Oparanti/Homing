import { Suspense } from "react";

import { ThreadView } from "@/components/threads/thread-view";

export default function ThreadPage() {
  return (
    <Suspense fallback={<p className="text-ink-2">Opening this goal…</p>}>
      <ThreadView />
    </Suspense>
  );
}
