import { ImportView } from "@/components/imports/import-view";
import { PageTitle } from "@/components/shell/empty-state";

export default function ImportPage() {
  return (
    <>
      <PageTitle title="Import from WhatsApp" subtitle="Bring in everything you've sent yourself. Each save keeps the day you sent it." />
      <ImportView />
    </>
  );
}
