"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { FUNDING_TOKEN_SYMBOL, SUPPORTED_NETWORKS } from "@/lib/constants";
import { getBrandProfile, getQuote } from "@/services/brand";
import { createCampaign, launchCampaign } from "@/services/campaigns";
import type { BrandProfile, BrandQuote, Campaign } from "@/types";

/**
 * Brand-side campaign creation (Spec 02).
 *
 * A campaign is a promise about money, so the form asks for the money up front
 * and holds the brand to the same rules the backend enforces: only a fixed
 * reward per verified original post, a budget that covers at least one payout,
 * and a window that ends after it starts. Those rules are duplicated here only
 * to fail fast and to place the message next to the field; the backend remains
 * the authority, and any message it returns is surfaced verbatim.
 *
 * The screen serves two callers. A brand creates a campaign that the backend
 * attributes to that brand by itself (the payload carries no brand id), and the
 * draft cannot go live until the brand's confirmed stablecoin covers the budget
 * plus the fee. Staff create a platform-funded campaign with no funding gate, so
 * the funding guidance is shown only to a brand.
 */
export default function BrandCreateCampaignPage() {
  const { user, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!user) {
        if (active) setLoaded(true);
        return;
      }
      try {
        const next = await getBrandProfile();
        if (active) setProfile(next);
      } catch {
        if (active) setProfile(null);
      } finally {
        if (active) setLoaded(true);
      }
    })();
    return () => {
      active = false;
    };
  }, [user]);

  if (authLoading || (user && !loaded)) {
    return (
      <div className="container section">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container section">
        <div className="card">
          <h1>Create a campaign</h1>
          <p className="muted">
            Sign in to create a campaign and fund creator payouts.
          </p>
          <div className="row">
            <Link href="/dashboard" className="btn btn-primary">
              Sign in
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isStaff = user.is_staff;

  // A brand must exist before a campaign can be attributed to it. Staff create
  // platform-funded campaigns, so they are allowed through without one.
  if (!profile && !isStaff) {
    return (
      <div className="container section" style={{ maxWidth: 680 }}>
        <h1>Create a campaign</h1>
        <div className="card">
          <h3>Set up your brand first</h3>
          <p className="muted">
            A campaign is funded by the brand that owns it. Create your brand
            profile, then come back to launch a campaign from its balance.
          </p>
          <div className="row">
            <Link href="/brand" className="btn btn-primary">
              Go to brand setup
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container section" style={{ maxWidth: 820 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Create a campaign</h1>
          <p className="muted">
            {profile
              ? `Funded by ${profile.company_name}`
              : "Platform-funded campaign (staff)"}
          </p>
        </div>
        <Link href="/brand" className="btn btn-ghost btn-sm">
          Back to dashboard
        </Link>
      </div>

      <CampaignForm
        isBrand={Boolean(profile)}
        brandActive={profile?.status === "ACTIVE"}
      />
    </div>
  );
}

interface FormState {
  name: string;
  slug: string;
  slugEdited: boolean;
  description: string;
  project_name: string;
  token_symbol: string;
  chain_id: string;
  reward_rate: string;
  budget: string;
  maximum_reward_per_seller: string;
  maximum_rewards_per_seller: string;
  start_at: string;
  end_at: string;
  required_hashtags: string;
  required_disclosure: string;
}

type FieldErrors = Partial<Record<keyof FormState, string>>;

const EMPTY_FORM: FormState = {
  name: "",
  slug: "",
  slugEdited: false,
  description: "",
  project_name: "",
  token_symbol: FUNDING_TOKEN_SYMBOL,
  chain_id: String(SUPPORTED_NETWORKS[0].chainId),
  reward_rate: "",
  budget: "",
  maximum_reward_per_seller: "",
  maximum_rewards_per_seller: "",
  start_at: "",
  end_at: "",
  required_hashtags: "",
  required_disclosure: "",
};

/** Lowercase, hyphenated slug matching the backend SlugField (`a-z0-9-`). */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 200);
}

/** `datetime-local` needs local wall-clock time, not a UTC ISO string. */
function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** Split a comma-separated input into a clean, de-duplicated list. */
function splitList(value: string): string[] {
  const seen = new Set<string>();
  for (const raw of value.split(",")) {
    const item = raw.trim();
    if (item) seen.add(item);
  }
  return Array.from(seen);
}

/**
 * Client-side validation that mirrors `_validate_campaign_fields` on the
 * backend. It exists to fail fast and to place the message beside the field;
 * the backend is still the authority and its errors are shown as returned.
 */
function validate(form: FormState): FieldErrors {
  const errors: FieldErrors = {};
  const rate = Number(form.reward_rate);
  const budget = Number(form.budget);
  const maxReward =
    form.maximum_reward_per_seller.trim() === ""
      ? null
      : Number(form.maximum_reward_per_seller);
  const maxRewards =
    form.maximum_rewards_per_seller.trim() === ""
      ? null
      : Number(form.maximum_rewards_per_seller);

  if (!form.name.trim()) errors.name = "A campaign name is required.";
  if (!form.slug.trim()) errors.slug = "A URL slug is required.";
  else if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(form.slug)) {
    errors.slug = "Use lowercase letters, numbers and hyphens only.";
  }
  if (!form.project_name.trim()) errors.project_name = "A project name is required.";
  if (!form.token_symbol.trim()) errors.token_symbol = "A payout token is required.";
  if (!Number.isInteger(Number(form.chain_id))) {
    errors.chain_id = "A numeric chain id is required.";
  }

  if (!form.reward_rate.trim() || !Number.isFinite(rate)) {
    errors.reward_rate = "A fixed reward per post is required.";
  } else if (rate <= 0) {
    errors.reward_rate = "A fixed reward per post must be greater than zero.";
  }

  if (!form.budget.trim() || !Number.isFinite(budget)) {
    errors.budget = "A budget is required.";
  } else if (budget <= 0) {
    errors.budget = "Campaign budget must be greater than zero.";
  } else if (Number.isFinite(rate) && rate > 0 && budget < rate) {
    errors.budget =
      "Budget must cover at least one reward, or no verified post could be paid.";
  }

  if (maxReward !== null && (!Number.isFinite(maxReward) || maxReward < 0)) {
    errors.maximum_reward_per_seller = "Must be zero or a positive amount.";
  } else if (
    maxReward !== null &&
    maxReward > 0 &&
    Number.isFinite(rate) &&
    rate > 0 &&
    maxReward < rate
  ) {
    errors.maximum_reward_per_seller =
      "Below the per-post reward, so a qualifying post could not be paid.";
  }

  if (maxRewards !== null && (!Number.isInteger(maxRewards) || maxRewards < 0)) {
    errors.maximum_rewards_per_seller = "Must be a whole number.";
  } else if (
    maxRewards !== null &&
    maxRewards > 0 &&
    Number.isFinite(rate) &&
    rate > 0 &&
    Number.isFinite(budget) &&
    budget > maxRewards * rate
  ) {
    errors.maximum_rewards_per_seller =
      "Budget exceeds cap × reward, so the surplus could never be paid out.";
  }

  if (!form.start_at) errors.start_at = "A start time is required.";
  if (!form.end_at) errors.end_at = "An end time is required.";
  if (form.start_at && form.end_at) {
    const start = new Date(form.start_at).getTime();
    const end = new Date(form.end_at).getTime();
    if (Number.isFinite(start) && Number.isFinite(end) && end <= start) {
      errors.end_at = "The end time must be after the start time.";
    }
  }

  return errors;
}

function CampaignForm({
  isBrand,
  brandActive,
}: {
  isBrand: boolean;
  brandActive: boolean;
}) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<Campaign | null>(null);

  // Prefill a sensible window on the client only, so SSR and the first client
  // render agree and hydration does not mismatch.
  useEffect(() => {
    const now = new Date();
    const end = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    setForm((prev) => ({
      ...prev,
      start_at: prev.start_at || toLocalInputValue(now),
      end_at: prev.end_at || toLocalInputValue(end),
    }));
  }, []);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      // Keep the slug in step with the name until the brand edits it directly.
      if (key === "name" && !prev.slugEdited) {
        next.slug = slugify(String(value));
      }
      if (key === "slug") next.slugEdited = true;
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const nextErrors = validate(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    const requirements: Record<string, unknown> = {};
    const hashtags = splitList(form.required_hashtags);
    const disclosure = splitList(form.required_disclosure);
    if (hashtags.length) requirements.required_hashtags = hashtags;
    if (disclosure.length) requirements.required_disclosure = disclosure;

    setBusy(true);
    try {
      const campaign = await createCampaign({
        name: form.name.trim(),
        slug: form.slug.trim(),
        description: form.description.trim(),
        project_name: form.project_name.trim(),
        token_symbol: form.token_symbol.trim().toUpperCase(),
        chain_id: Number(form.chain_id),
        budget: form.budget.trim(),
        // Only a fixed reward per verified original post is offered at launch.
        reward_model: "FIXED",
        reward_rate: form.reward_rate.trim(),
        maximum_reward_per_seller: form.maximum_reward_per_seller.trim() || undefined,
        maximum_rewards_per_seller:
          form.maximum_rewards_per_seller.trim() === ""
            ? undefined
            : Number(form.maximum_rewards_per_seller),
        start_at: new Date(form.start_at).toISOString(),
        end_at: new Date(form.end_at).toISOString(),
        requirements_json: requirements,
      });
      setCreated(campaign);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the campaign.");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return <CreatedPanel campaign={created} isBrand={isBrand} />;
  }

  return (
    <form className="card" onSubmit={handleSubmit} style={{ marginTop: 20 }}>
      {isBrand && !brandActive && (
        <div className="banner banner-error">
          Your brand is pending review. You can create a draft, but it cannot be
          launched until staff activate your brand.
        </div>
      )}

      <h3>Campaign</h3>
      <label className="field">
        Campaign name
        <input
          type="text"
          required
          placeholder="Robinhood Chain Launch"
          value={form.name}
          onChange={(e) => update("name", e.target.value)}
        />
        {errors.name && <span className="banner banner-error">{errors.name}</span>}
      </label>

      <label className="field">
        URL slug
        <input
          type="text"
          required
          placeholder="rh-launch"
          value={form.slug}
          onChange={(e) => update("slug", e.target.value)}
        />
        {errors.slug && <span className="banner banner-error">{errors.slug}</span>}
      </label>

      <label className="field">
        Project name
        <input
          type="text"
          required
          placeholder="Robinhood Chain"
          value={form.project_name}
          onChange={(e) => update("project_name", e.target.value)}
        />
        {errors.project_name && (
          <span className="banner banner-error">{errors.project_name}</span>
        )}
      </label>

      <label className="field">
        Description
        <textarea
          rows={3}
          placeholder="What creators should post about."
          value={form.description}
          onChange={(e) => update("description", e.target.value)}
        />
      </label>

      <div className="grid grid-3">
        <label className="field">
          Payout token
          <input
            type="text"
            required
            value={form.token_symbol}
            onChange={(e) => update("token_symbol", e.target.value)}
          />
          {errors.token_symbol && (
            <span className="banner banner-error">{errors.token_symbol}</span>
          )}
        </label>
        <label className="field">
          Chain
          <select
            value={form.chain_id}
            onChange={(e) => update("chain_id", e.target.value)}
          >
            {SUPPORTED_NETWORKS.map((network) => (
              <option key={network.chainId} value={network.chainId}>
                {network.name} ({network.chainId})
              </option>
            ))}
          </select>
          {errors.chain_id && (
            <span className="banner banner-error">{errors.chain_id}</span>
          )}
        </label>
        <label className="field">
          Reward model
          <input type="text" value="Fixed per verified post" readOnly />
        </label>
      </div>

      <h3 style={{ marginTop: 8 }}>Money</h3>
      <p className="muted">
        Rewards are a fixed amount per verified, original post. The platform fee
        is added on top of the budget when you fund — it is never taken out of a
        creator&apos;s payout.
      </p>
      <div className="grid grid-3">
        <label className="field">
          Reward per post ({form.token_symbol || FUNDING_TOKEN_SYMBOL})
          <input
            type="text"
            inputMode="decimal"
            required
            placeholder="4.50"
            value={form.reward_rate}
            onChange={(e) => update("reward_rate", e.target.value)}
          />
          {errors.reward_rate && (
            <span className="banner banner-error">{errors.reward_rate}</span>
          )}
        </label>
        <label className="field">
          Total budget ({form.token_symbol || FUNDING_TOKEN_SYMBOL})
          <input
            type="text"
            inputMode="decimal"
            required
            placeholder="15000.00"
            value={form.budget}
            onChange={(e) => update("budget", e.target.value)}
          />
          {errors.budget && (
            <span className="banner banner-error">{errors.budget}</span>
          )}
        </label>
        <label className="field">
          Max reward per creator (optional)
          <input
            type="text"
            inputMode="decimal"
            placeholder="50.00"
            value={form.maximum_reward_per_seller}
            onChange={(e) => update("maximum_reward_per_seller", e.target.value)}
          />
          {errors.maximum_reward_per_seller && (
            <span className="banner banner-error">
              {errors.maximum_reward_per_seller}
            </span>
          )}
        </label>
      </div>
      <label className="field">
        Max rewards per creator (optional)
        <input
          type="number"
          min={0}
          placeholder="10"
          value={form.maximum_rewards_per_seller}
          onChange={(e) => update("maximum_rewards_per_seller", e.target.value)}
        />
        {errors.maximum_rewards_per_seller && (
          <span className="banner banner-error">
            {errors.maximum_rewards_per_seller}
          </span>
        )}
      </label>

      <h3 style={{ marginTop: 8 }}>Window</h3>
      <div className="grid grid-3">
        <label className="field">
          Starts
          <input
            type="datetime-local"
            required
            value={form.start_at}
            onChange={(e) => update("start_at", e.target.value)}
          />
          {errors.start_at && (
            <span className="banner banner-error">{errors.start_at}</span>
          )}
        </label>
        <label className="field">
          Ends
          <input
            type="datetime-local"
            required
            value={form.end_at}
            onChange={(e) => update("end_at", e.target.value)}
          />
          {errors.end_at && (
            <span className="banner banner-error">{errors.end_at}</span>
          )}
        </label>
      </div>

      <h3 style={{ marginTop: 8 }}>Post requirements (optional)</h3>
      <div className="grid grid-3">
        <label className="field">
          Required hashtags
          <input
            type="text"
            placeholder="#ad, #robinhoodchain"
            value={form.required_hashtags}
            onChange={(e) => update("required_hashtags", e.target.value)}
          />
        </label>
        <label className="field">
          Required disclosure
          <input
            type="text"
            placeholder="#ad"
            value={form.required_disclosure}
            onChange={(e) => update("required_disclosure", e.target.value)}
          />
        </label>
      </div>
      <p className="muted">
        Comma-separated. Requirements are matching signals, not proof of
        authorship; rewards are paid only for original, disclosed posts.
      </p>

      {error && <div className="banner banner-error">{error}</div>}

      <button className="btn btn-primary" disabled={busy}>
        {busy ? "Creating…" : "Create draft campaign"}
      </button>
    </form>
  );
}

/**
 * Confirmation step.
 *
 * The campaign is created as a DRAFT: it does not accept creators until it is
 * launched, and a brand's draft cannot be launched until its confirmed balance
 * covers the budget plus the fee. Rather than pretend otherwise, this panel
 * quotes the real cost from the backend and lets the launch attempt report the
 * shortfall as the backend words it.
 */
function CreatedPanel({ campaign, isBrand }: { campaign: Campaign; isBrand: boolean }) {
  const [quote, setQuote] = useState<BrandQuote | null>(null);
  const [status, setStatus] = useState(campaign.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!isBrand) return;
    let active = true;
    (async () => {
      try {
        const next = await getQuote(campaign.budget);
        if (active) setQuote(next);
      } catch {
        // A missing quote is not fatal: the launch attempt is the source of
        // truth about whether the campaign is funded.
      }
    })();
    return () => {
      active = false;
    };
  }, [campaign.budget, isBrand]);

  async function handleLaunch() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const launched = await launchCampaign(campaign.slug);
      setStatus(launched.status);
      setNotice("Campaign is live. Creators can join it now.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not launch the campaign.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>Campaign created</h3>
        <span className={status === "ACTIVE" ? "badge badge-ok" : "badge"}>
          {status}
        </span>
      </div>
      <ul className="stats-list">
        <li>
          <span className="muted">Name</span>
          <br />
          <strong>{campaign.name}</strong>
        </li>
        <li>
          <span className="muted">Slug</span>
          <br />
          <code className="wallet-chip">{campaign.slug}</code>
        </li>
        <li>
          <span className="muted">Reward / post</span>
          <br />
          <strong>
            {formatAmount(campaign.reward_rate)} {campaign.token_symbol}
          </strong>
        </li>
        <li>
          <span className="muted">Budget</span>
          <br />
          <strong>
            {formatAmount(campaign.budget)} {campaign.token_symbol}
          </strong>
        </li>
      </ul>

      {isBrand && quote && (
        <ul className="stats-list" style={{ marginTop: 16 }}>
          <li>
            <span className="muted">Creator payouts</span>
            <br />
            <strong>{formatAmount(quote.payout_total)}</strong>
          </li>
          <li>
            <span className="muted">
              Platform fee ({quote.platform_fee_bps / 100}%)
            </span>
            <br />
            <strong>{formatAmount(quote.platform_fee)}</strong>
          </li>
          <li>
            <span className="muted">Total to fund</span>
            <br />
            <strong>{formatAmount(quote.total_required)}</strong>
          </li>
          <li>
            {quote.sufficient ? (
              <span className="badge badge-ok">Funded</span>
            ) : (
              <span className="badge">
                Short by {formatAmount(quote.shortfall)}
              </span>
            )}
          </li>
        </ul>
      )}

      {isBrand && quote && !quote.sufficient && (
        <p className="muted">
          Fund your brand balance with the shortfall above before launching.
          Launching an unfunded campaign is refused, so creators are never asked
          to work for money that is not there.
        </p>
      )}

      {notice && <div className="stat-note">{notice}</div>}
      {error && <div className="banner banner-error">{error}</div>}

      <div className="row" style={{ marginTop: 16 }}>
        {status !== "ACTIVE" && (
          <button
            className="btn btn-primary btn-sm"
            onClick={() => void handleLaunch()}
            disabled={busy}
          >
            {busy ? "Launching…" : "Launch campaign"}
          </button>
        )}
        <Link href="/brand" className="btn btn-outline btn-sm">
          {isBrand && quote && !quote.sufficient
            ? "Fund brand balance"
            : "Back to dashboard"}
        </Link>
        <Link href="/brand/create" className="btn btn-ghost btn-sm">
          Create another
        </Link>
      </div>
    </div>
  );
}

/** Trim trailing zeros: the API returns 18-decimal strings because the money
 *  arithmetic runs in token units, and "575.000000000000000000" reads as a bug. */
function formatAmount(value: string): string {
  const num = Number(value);
  if (!Number.isFinite(num)) return value;
  return num.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
