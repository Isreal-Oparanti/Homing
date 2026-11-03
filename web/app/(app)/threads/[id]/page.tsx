import { Suspense } from "react";

import { ThreadView } from "@/components/threads/thread-view";
import { Loading } from "@/components/shell/loading";

export default function ThreadPage() {
  return (
    <Suspense fallback={<Loading label="Opening this goal…" />}>
      <ThreadView />
    </Suspense>
  );
}
