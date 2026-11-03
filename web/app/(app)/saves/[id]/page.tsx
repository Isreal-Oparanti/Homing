import { Suspense } from "react";

import { SaveCardView } from "@/components/saves/save-card";
import { Loading } from "@/components/shell/loading";

export default function SavePage() {
  return (
    <Suspense fallback={<Loading label="Opening your save…" />}>
      <SaveCardView />
    </Suspense>
  );
}
