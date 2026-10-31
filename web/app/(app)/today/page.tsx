import { EmptyState, PageTitle } from "@/components/shell/empty-state";

export default function TodayPage() {
  return (
    <>
      <PageTitle title="Today" subtitle="At most three things that need you now." />
      <EmptyState
        title="Nothing needs you yet."
        body="When something you saved matters, it comes back here with the next step."
      />
    </>
  );
}
