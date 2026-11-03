import { Suspense } from "react";

import { AskView } from "@/components/search/ask-view";
import { Loading } from "@/components/shell/loading";

export default function AskPage() {
  return (
    <Suspense fallback={<Loading label="Opening your question…" />}>
      <AskView />
    </Suspense>
  );
}
