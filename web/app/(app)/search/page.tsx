import { EmptyState, PageTitle } from "@/components/shell/empty-state";

export default function SearchPage() {
  return (
    <>
      <PageTitle title="Search and ask" subtitle="Find a save by meaning, or ask about your saves." />
      <EmptyState
        title="Nothing to search yet."
        body="Search and Ask work over your saves once you've added some."
      />
    </>
  );
}
