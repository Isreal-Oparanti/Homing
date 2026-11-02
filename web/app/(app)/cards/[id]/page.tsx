import { Suspense } from "react";

import { PrepView } from "@/components/today/prep-view";

export default function CardPage() {
  return (
    <Suspense fallback={<p className="text-ink-2">Opening this card…</p>}>
      <PrepView />
    </Suspense>
  );
}
