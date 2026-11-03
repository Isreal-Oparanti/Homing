import { TeamFeed } from "@/components/team/team-feed";

export default function AgentsPage() {
  return <TeamFeed showDevTools={process.env.NODE_ENV === "development"} />;
}
