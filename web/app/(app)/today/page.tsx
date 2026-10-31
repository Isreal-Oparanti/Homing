import { PageTitle } from "@/components/shell/empty-state";
import { TodayList } from "@/components/today/today-list";

export default function TodayPage() {
  return (
    <>
      <PageTitle title="Today" subtitle="At most three things that need you now." />
      <TodayList />
    </>
  );
}
