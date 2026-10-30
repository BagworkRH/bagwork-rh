/**
 * Human wording for backend enums.
 *
 * The API speaks in enums (`NOT_ORIGINAL`, `REAUTH_REQUIRED`); creators do not.
 * Every status a creator can see is translated here, in one place, so no screen
 * can leak a raw code by accident - and each rejection says what to do about it,
 * because a rejection a creator cannot act on is just a support ticket.
 */
export type StatusTone = "pending" | "ok" | "bad" | "hold";

export type StatusCopy = {
  /** Short label for a badge. */
  text: string;
  tone: StatusTone;
  /** Why it is not payable, in the creator's own terms. */
  reason?: string;
};

/** Badge classes that exist in globals.css. */
export function toneClass(tone: StatusTone): string {
  if (tone === "ok") return "badge badge-ok";
  if (tone === "bad") return "badge badge-danger";
  if (tone === "hold") return "badge badge-token";
  return "badge";
}

/**
 * Every value of `PostVerificationStatus`. "Checking" covers the several
 * pipeline stages a creator has no reason to tell apart.
 */
const POST_STATUS: Record<string, StatusCopy> = {
  DISCOVERED: { text: "Checking", tone: "pending" },
  BASIC_VALIDATION: { text: "Checking", tone: "pending" },
  CAMPAIGN_MATCH: { text: "Checking", tone: "pending" },
  DUPLICATE_CHECK: { text: "Checking", tone: "pending" },
  METRICS_PENDING: { text: "Checking", tone: "pending" },
  VERIFIED: { text: "Payable", tone: "ok" },
  REWARD_CALCULATED: { text: "Payable", tone: "ok" },
  APPROVED: { text: "Payable", tone: "ok" },
  NOT_ORIGINAL: {
    text: "Not payable",
    tone: "bad",
    reason:
      "This is a repost or a quote of someone else's post. Only posts you wrote yourself earn.",
  },
  DUPLICATE: {
    text: "Not payable",
    tone: "bad",
    reason: "This post has already been paid once.",
  },
  OUTSIDE_CAMPAIGN_WINDOW: {
    text: "Not payable",
    tone: "bad",
    reason: "It was published outside the campaign's dates.",
  },
  REQUIREMENT_MISSING: {
    text: "Not payable",
    tone: "bad",
    reason:
      "The campaign asks for specific text or a hashtag, and this post is missing it.",
  },
  NOT_DISCLOSED: {
    text: "Not payable",
    tone: "bad",
    reason:
      "The campaign requires a disclosure (for example #ad), and this post is missing it.",
  },
  NOT_ELIGIBLE: {
    text: "Not payable",
    tone: "bad",
    reason: "This post does not meet the campaign's rules.",
  },
  ACCOUNT_NOT_CONNECTED: {
    text: "Action needed",
    tone: "bad",
    reason: "Connect the account you posted from so this post can be paid.",
  },
  PROVIDER_ERROR: {
    text: "Could not check yet",
    tone: "pending",
    reason: "We could not read this post from the platform. We will try again.",
  },
  SUSPICIOUS_ACTIVITY: {
    text: "Held for review",
    tone: "hold",
    reason: "A person is checking this one before it is paid.",
  },
};

/** Never show a raw enum: an unknown status still reads like a sentence. */
const POST_FALLBACK: StatusCopy = {
  text: "Checking",
  tone: "pending",
  reason: "We are still working out whether this post can be paid.",
};

export function postStatus(status: string): StatusCopy {
  return POST_STATUS[status] ?? POST_FALLBACK;
}

/**
 * Account status, plus whether the creator has to act.
 *
 * `REAUTH_REQUIRED` is the one that matters: the connection is dead and nothing
 * will be found for that account until its owner reconnects, so the UI has to
 * say so rather than leave the creator quietly earning nothing.
 */
export function accountStatus(status: string): { text: string; needsReconnect: boolean } {
  switch (status) {
    case "CONNECTED":
      return { text: "Connected", needsReconnect: false };
    case "REAUTH_REQUIRED":
      return { text: "Reconnect needed", needsReconnect: true };
    case "DISCONNECTED":
      return { text: "Disconnected", needsReconnect: true };
    case "REVOKED":
      return { text: "Access revoked", needsReconnect: true };
    case "PENDING":
      return { text: "Connecting…", needsReconnect: false };
    case "ERROR":
      return { text: "Something went wrong", needsReconnect: true };
    default:
      return { text: "Not connected", needsReconnect: true };
  }
}

/**
 * The backend sends an error *code* back to the onboarding page. `invalid_state`
 * is the one creators actually hit (the connect link expires after ten minutes),
 * and it is also the one that reads worst raw - it looks like their fault.
 */
export function describeOauthError(code: string): { text: string; detail?: string } {
  if (code === "invalid_state") {
    return {
      text: "That connection link expired before it was used. Connect again and finish within ten minutes.",
      detail: "invalid_state",
    };
  }
  if (code === "no_seller") {
    return {
      text: "Finish creating your creator profile, then connect your account.",
      detail: "no_seller",
    };
  }
  if (code === "unexpected_error") {
    return {
      text: "Something went wrong on our side. Try connecting again.",
      detail: "unexpected_error",
    };
  }
  if (/401|403|token exchange/i.test(code)) {
    return {
      text: "X refused the connection. Try again, and check that the app is still authorised in your X settings.",
      detail: code,
    };
  }
  return {
    text: "We could not connect that account. Try again.",
    detail: code,
  };
}
