"use client";

import { useCallback, useEffect, useState } from "react";

import { getSettings } from "@/services/admin";
import type { OpsSettings } from "@/types/ops";

/**
 * Platform settings, read-only.
 *
 * This screen reports whether the chain wiring is *configured*, never the
 * values that must stay secret. There is deliberately no endpoint that returns
 * the signer key, so nothing here can leak one into a browser.
 */
export default function OpsSettingsPage() {
  const [data, setData] = useState<OpsSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getSettings());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <p className="muted">Loading settings…</p>;
  if (error) return <div className="banner banner-error">{error}</div>;
  if (!data) return null;

  return (
    <>
      <div className="grid">
        <div className="card">
          <h3>Platform control</h3>
          <p>
            Claiming:{" "}
            <span className={data.claiming_paused ? "badge badge-danger" : "badge badge-ok"}>
              {data.claiming_paused ? "PAUSED" : "ENABLED"}
            </span>
          </p>
          <p className="muted">
            The pause switch lives in Django admin. Pausing stops every new claim platform-wide;
            existing confirmed claims are unaffected.
          </p>
        </div>

        <div className="card">
          <h3>Chain</h3>
          <dl className="stats-list">
            <div>
              <dt>Chain id</dt>
              <dd>{data.chain.chain_id}</dd>
            </div>
            <div>
              <dt>RPC</dt>
              <dd>{data.chain.rpc_configured ? "configured" : "missing"}</dd>
            </div>
            <div>
              <dt>Signer</dt>
              <dd>{data.chain.signer_configured ? "configured" : "missing"}</dd>
            </div>
            <div>
              <dt>Escrow</dt>
              <dd style={{ overflowWrap: "anywhere" }}>{data.chain.contract_address}</dd>
            </div>
            <div>
              <dt>Reward token</dt>
              <dd style={{ overflowWrap: "anywhere" }}>{data.chain.reward_token_address}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="card">
        <h3>Risk configuration</h3>
        <p>
          Review threshold: <strong>{data.risk.review_threshold}</strong>
        </p>
        <p className="muted">
          Signal weights:{" "}
          {Object.entries(data.risk.signal_weights)
            .map(([key, value]) => `${key} ${value}`)
            .join(" · ")}
        </p>
      </div>

      <div className="card">
        <h3>Token allowlist</h3>
        {data.tokens.length === 0 ? (
          <p className="muted">No tokens are allowlisted.</p>
        ) : (
          <div className="table-cards">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Chain</th>
                  <th>Address</th>
                  <th>Decimals</th>
                  <th>Enabled</th>
                </tr>
              </thead>
              <tbody>
                {data.tokens.map((token) => (
                  <tr key={token.id}>
                    <td data-label="Symbol">
                      <strong>{token.symbol}</strong>
                    </td>
                    <td data-label="Chain">{token.chain_id}</td>
                    <td data-label="Address">
                      <code style={{ overflowWrap: "anywhere" }}>{token.address}</code>
                    </td>
                    <td data-label="Decimals">{token.decimals}</td>
                    <td data-label="Enabled">
                      <span className={token.enabled ? "badge badge-ok" : "badge"}>
                        {token.enabled ? "yes" : "no"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">
          Only allowlisted tokens can fund a campaign. Changes are made in Django admin.
        </p>
      </div>
    </>
  );
}
