import { SaveList } from "@/components/saves/save-list";
import { PageTitle } from "@/components/shell/empty-state";
import { ThreadList } from "@/components/threads/thread-list";

export default function ThreadsPage() {
  return (
    <>
      <PageTitle title="Threads" subtitle="The goals your saves serve." />
      <ThreadList />
      <SaveList />
    </>
  );
}
