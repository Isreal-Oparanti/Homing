import { Suspense } from "react";

import { PrepView } from "@/components/today/prep-view";
import { Loading } from "@/components/shell/loading";

export default function CardPage() {
  return (
    <Suspense fallback={<Loading label="Opening this card…" />}>
      <PrepView />
    </Suspense>
  );
}
