import CampaignsExplorer from "@/components/CampaignsExplorer";
import { CompassIcon } from "@/components/icons";
import { EmptyState } from "@/components/ui";
import { apiRequest } from "@/lib/api";
import type { Campaign } from "@/types";

async function getCampaigns(): Promise<Campaign[]> {
  try {
    return await apiRequest<Campaign[]>("/api/v1/campaigns/");
  } catch {
    return [];
  }
}

export const metadata = { title: "Campaigns — bagworkRH" };

/**
 * The campaign marketplace.
 *
 * Server-rendered from the public endpoint so the list is real on first paint;
 * the search/filter/sort view is layered on by the client explorer. `?q=` is
 * read here so the topbar search can deep-link straight into a filtered list.
 */
export default async function CampaignsPage({
  searchParams,
}: {
  searchParams?: { [key: string]: string | string[] | undefined };
}) {
  const campaigns = await getCampaigns();
  const raw = searchParams?.q;
  const initialQuery = typeof raw === "string" ? raw : "";

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head">
        <div>
          <span className="eyebrow">Discover</span>
          <h1>Campaign marketplace</h1>
          <p className="lede">
            Find a campaign, publish an original post, and earn verified token rewards.
          </p>
        </div>
      </div>

      {campaigns.length === 0 ? (
        <EmptyState icon={CompassIcon} title="No campaigns right now">
          Campaigns appear here the moment a brand launches one. Check back soon.
        </EmptyState>
      ) : (
        <CampaignsExplorer campaigns={campaigns} initialQuery={initialQuery} />
      )}
    </div>
  );
}
