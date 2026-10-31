import { Suspense } from "react";

import { SaveCardView } from "@/components/saves/save-card";

export default function SavePage() {
  return (
    <Suspense fallback={<p className="text-ink-2">Opening your save…</p>}>
      <SaveCardView />
    </Suspense>
  );
}
