import { redirect } from "next/navigation";

/** The team is now Your agents; old links still land there. */
export default function TeamPage() {
  redirect("/agents");
}
