import { Suspense } from "react";

import { AskView } from "@/components/search/ask-view";

export default function AskPage() {
  return (
    <Suspense fallback={<p className="text-ink-2">Opening your question…</p>}>
      <AskView />
    </Suspense>
  );
}
