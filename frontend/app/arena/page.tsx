import { redirect } from "next/navigation";

/**
 * The arena was the leaderboard's first name. Kept as a redirect so any link
 * shared before the rename still lands on something real.
 */
export default function ArenaRedirect() {
  redirect("/leaderboard");
}
