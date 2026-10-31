import { SaveList } from "@/components/saves/save-list";
import { EmptyState, PageTitle } from "@/components/shell/empty-state";

export default function ThreadsPage() {
  return (
    <>
      <PageTitle title="Threads" subtitle="The goals your saves serve." />
      <EmptyState
        title="No threads yet."
        body="As you save things, Homing groups them by what they're for."
      />
      <SaveList />
    </>
  );
}
