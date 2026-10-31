import { ProfileView } from "@/components/profile/profile-view";
import { PageTitle } from "@/components/shell/empty-state";

export default function ProfilePage() {
  return (
    <>
      <PageTitle title="What Homing knows about you" subtitle="From your answers on save cards. Change or forget anything." />
      <ProfileView />
    </>
  );
}
