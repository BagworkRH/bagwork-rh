"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import * as brandApi from "@/services/brand";
import { FUNDING_TOKEN_SYMBOL, shortenAddress } from "@/lib/constants";
import { formatAmount } from "@/lib/money";
import type {
  BrandCampaignFunding,
  BrandFunding,
  BrandProfile,
  BrandQuote,
} from "@/types";

/**
 * Brand dashboard: onboarding, stablecoin funding, and campaign cost.
 *
 * A brand is the paying customer, so this surface is deliberately separate from
 * the seller dashboard: a brand's balance is money it has committed, not money
 * it has earned.
 *
 * The page preserves a distinction the API enforces — a *recorded* deposit is
 * PENDING and does not count toward the funded balance until confirmed
 * on-chain. Showing a pending deposit as though it were spendable would tell a
 * brand it has budget it does not.
 */
export default function BrandDashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [fundings, setFundings] = useState<BrandFunding[]>([]);
  const [campaigns, setCampaigns] = useState<BrandCampaignFunding[]>([]);
  const [balance, setBalance] = useState("0");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const nextProfile = await brandApi.getBrandProfile();
      setProfile(nextProfile);
      if (!nextProfile) {
        setFundings([]);
        setCampaigns([]);
        setBalance("0");
        return;
      }
      const [fundingList, campaignList] = await Promise.all([
        brandApi.listFunding(),
        brandApi.listBrandCampaigns(),
      ]);
      setFundings(fundingList.fundings);
      setBalance(fundingList.confirmed_balance);
      setCampaigns(campaignList.campaigns);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your brand.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      void refresh();
    } else {
      setLoading(false);
    }
  }, [user, refresh]);

  if (authLoading || (user && loading)) {
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
          <h1>Brand dashboard</h1>
          <p className="muted">
            Sign in to fund campaigns, see what each one costs, and track your
            committed balance.
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

  if (!profile) {
    return (
      <BrandOnboard
        onCreated={() => void refresh()}
        error={error}
        setError={setError}
      />
    );
  }

  return (
    <div className="container section">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>{profile.company_name}</h1>
          <p className="muted">Brand dashboard</p>
        </div>
        <div className="row">
          <span className={profile.status === "ACTIVE" ? "badge badge-ok" : "badge"}>
            {profile.status}
          </span>
          <Link href="/brand/create" className="btn btn-primary btn-sm">
            Create a campaign
          </Link>
        </div>
      </div>

      {profile.status !== "ACTIVE" && (
        <div className="banner banner-error">{statusHint(profile.status)}</div>
      )}

      <div className="stat-strip" style={{ marginTop: 20 }}>
        <div className="stat-box">
          <div className="num">{formatAmount(balance)}</div>
          <div className="muted">Confirmed {FUNDING_TOKEN_SYMBOL} balance</div>
        </div>
        <div className="stat-box">
          <div className="num">{String(campaigns.length)}</div>
          <div className="muted">Campaigns funded</div>
        </div>
        <div className="stat-box">
          <div className="num">
            {String(fundings.filter((f) => f.status === "PENDING").length)}
          </div>
          <div className="muted">Awaiting confirmation</div>
        </div>
      </div>

      <FundingPanel fundings={fundings} onChanged={refresh} />

      <div className="grid grid-2" style={{ marginTop: 20 }}>
        <QuotePanel />
        <div className="card">
          <h3>Your campaigns</h3>
          {campaigns.length === 0 ? (
            <p className="muted">
              Campaigns you fund appear here once a deposit is allocated to one.
            </p>
          ) : (
            <ul className="stats-list">
              {campaigns.map((c) => (
                <li key={c.slug}>
                  <strong>{c.name}</strong>
                  <span className="muted">
                    {" "}
                    — {formatAmount(c.funded)} funded of {formatAmount(c.budget)} budget
                    ({c.status})
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
    </div>
  );
}

function statusHint(status: string): string {
  if (status === "ACTIVE") return "Your brand is active.";
  if (status === "SUSPENDED") {
    return "This brand is suspended and cannot be funded. Contact support.";
  }
  return "Your brand is pending review. You can prepare funding, but staff activate brands after onboarding.";
}

/** First step: create the brand. Idempotent server-side, so a double-click
 *  cannot produce two brands for one user. */
function BrandOnboard({
  onCreated,
  error,
  setError,
}: {
  onCreated: () => void;
  error: string | null;
  setError: (value: string | null) => void;
}) {
  const [companyName, setCompanyName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [wallet, setWallet] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await brandApi.createBrandProfile({
        company_name: companyName,
        contact_email: contactEmail || undefined,
        funding_wallet: wallet || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create your brand.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container section" style={{ maxWidth: 680 }}>
      <h1>Set up your brand</h1>
      <p className="muted">
        Brands fund campaigns in {FUNDING_TOKEN_SYMBOL} and are charged only for verified, original,
        disclosed posts. Creators are paid in full from your deposit.
      </p>

      <form className="card" onSubmit={handleSubmit}>
        <label className="field">
          Company name
          <input
            type="text"
            required
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
          />
        </label>
        <label className="field">
          Billing contact email
          <input
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
          />
        </label>
        <label className="field">
          Funding wallet (optional)
          <input
            type="text"
            placeholder="0x…"
            value={wallet}
            onChange={(e) => setWallet(e.target.value)}
          />
        </label>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Creating…" : "Create brand"}
        </button>
      </form>

      {error && <div className="banner banner-error">{error}</div>}
    </div>
  );
}

/**
 * Funding panel: record a stablecoin deposit and confirm it.
 *
 * The two-step flow is deliberate and the copy says so. Recording a deposit
 * does not credit it; only confirmation does. Presenting a pending deposit as
 * funded would tell a brand it has budget it cannot spend.
 */
function FundingPanel({
  fundings,
  onChanged,
}: {
  fundings: BrandFunding[];
  onChanged: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [chainId, setChainId] = useState("46630");
  const [txHash, setTxHash] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleRecord(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await brandApi.recordFunding({
        amount,
        chain_id: Number(chainId),
        tx_hash: txHash.trim(),
        token_symbol: FUNDING_TOKEN_SYMBOL,
      });
      setNotice(
        "Deposit recorded. It does not count toward your balance until confirmed below."
      );
      setAmount("");
      setTxHash("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the deposit.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm(id: number) {
    setBusy(true);
    setError(null);
    try {
      await brandApi.confirmFunding(id);
      setNotice("Deposit confirmed and added to your balance.");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm the deposit.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 20 }}>
      <h3>Fund with {FUNDING_TOKEN_SYMBOL}</h3>
      <p className="muted">
        Send {FUNDING_TOKEN_SYMBOL} on Robinhood Chain, then record the transaction here. A recorded
        deposit stays pending until it is confirmed on-chain — it never counts as
        spendable budget before then.
      </p>

      <form onSubmit={handleRecord}>
        <div className="grid grid-3">
          <label className="field">
            Amount ({FUNDING_TOKEN_SYMBOL})
            <input
              type="text"
              inputMode="decimal"
              required
              placeholder="575.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <label className="field">
            Chain ID
            <input
              type="text"
              required
              value={chainId}
              onChange={(e) => setChainId(e.target.value)}
            />
          </label>
          <label className="field">
            Transaction hash
            <input
              type="text"
              required
              placeholder="0x…"
              value={txHash}
              onChange={(e) => setTxHash(e.target.value)}
            />
          </label>
        </div>
        <button className="btn btn-primary btn-sm" disabled={busy}>
          {busy ? "Working…" : "Record deposit"}
        </button>
      </form>

      {notice && <div className="stat-note">{notice}</div>}
      {error && <div className="banner banner-error">{error}</div>}

      {fundings.length > 0 && (
        <>
          <h3 style={{ marginTop: 20 }}>Deposits</h3>
          <ul className="stats-list">
            {fundings.map((f) => (
              <li key={f.id}>
                <strong>{formatAmount(f.amount)}</strong>
                <span className="muted"> on chain {f.chain_id} · </span>
                <code className="wallet-chip">{shortenAddress(f.tx_hash)}</code>{" "}
                {f.status === "CONFIRMED" ? (
                  <span className="badge badge-ok">Confirmed</span>
                ) : (
                  <>
                    <span className="badge">Pending</span>{" "}
                    <button
                      className="btn btn-outline btn-sm"
                      onClick={() => void handleConfirm(f.id)}
                      disabled={busy}
                    >
                      Confirm
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/**
 * Quote panel: what a campaign of a given size costs, fee included.
 *
 * Every figure comes from the backend rather than being computed in the
 * browser, so a brand is never shown a total the contract would reject as
 * under-funded.
 */
function QuotePanel() {
  const [payout, setPayout] = useState("");
  const [quote, setQuote] = useState<BrandQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleQuote(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setQuote(await brandApi.getQuote(payout));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build a quote.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>Campaign cost</h3>
      <p className="muted">
        Enter the total you want to pay creators. The platform fee is added on top —
        it is never taken out of a creator&apos;s payout.
      </p>

      <form onSubmit={handleQuote}>
        <label className="field">
          Total creator payouts ({FUNDING_TOKEN_SYMBOL})
          <input
            type="text"
            inputMode="decimal"
            required
            placeholder="500.00"
            value={payout}
            onChange={(e) => setPayout(e.target.value)}
          />
        </label>
        <button className="btn btn-outline btn-sm" disabled={busy}>
          {busy ? "Calculating…" : "Quote this campaign"}
        </button>
      </form>

      {error && <div className="banner banner-error">{error}</div>}

      {quote && (
        <ul className="stats-list" style={{ marginTop: 12 }}>
          <li>
            <span className="muted">Creator payouts</span>{" "}
            <strong>{formatAmount(quote.payout_total)}</strong>
          </li>
          <li>
            <span className="muted">
              Platform fee ({quote.platform_fee_bps / 100}%)
            </span>{" "}
            <strong>{formatAmount(quote.platform_fee)}</strong>
          </li>
          <li>
            <span className="muted">Total to fund</span>{" "}
            <strong>{formatAmount(quote.total_required)}</strong>
          </li>
          <li>
            <span className="muted">Your confirmed balance</span>{" "}
            <strong>{formatAmount(quote.already_funded)}</strong>
          </li>
          <li>
            {quote.sufficient ? (
              <span className="badge badge-ok">Funded</span>
            ) : (
              <span className="badge">Short by {formatAmount(quote.shortfall)}</span>
            )}
          </li>
        </ul>
      )}
    </div>
  );
}


