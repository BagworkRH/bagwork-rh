import CampaignCard from "@/components/CampaignCard";
import { apiRequest } from "@/lib/api";
import type { Campaign } from "@/types";

async function getCampaigns(): Promise<Campaign[]> {
  try {
    return await apiRequest<Campaign[]>("/api/v1/campaigns/");
  } catch {
    return [];
  }
}

export const metadata = { title: "Campaigns — CryptoRewards" };

export default async function CampaignsPage() {
  const campaigns = await getCampaigns();

  return (
    <div className="container section">
      <h1>Campaigns</h1>
      <p className="muted">
        Join active campaigns, publish qualifying posts, and earn token rewards.
      </p>

      {campaigns.length === 0 ? (
        <div className="card">
          <h3>No active campaigns right now</h3>
          <p className="muted">
            Campaigns appear here once they&apos;re live. Check back soon.
          </p>
        </div>
      ) : (
        <div className="grid">
          {campaigns.map((campaign) => (
            <CampaignCard key={campaign.id} campaign={campaign} />
          ))}
        </div>
      )}
    </div>
  );
}