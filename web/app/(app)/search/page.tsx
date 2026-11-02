import { SearchAsk } from "@/components/search/search-ask";
import { PageTitle } from "@/components/shell/empty-state";

export default function SearchPage() {
  return (
    <>
      <PageTitle title="Search and ask" subtitle="Find a save by meaning, or ask about your saves." />
      <SearchAsk />
    </>
  );
}
