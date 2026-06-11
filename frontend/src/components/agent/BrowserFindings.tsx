import type { BrandCheck, SensitiveSurface } from "./useBrowserCheckStream";
import "./BrowserFindings.css";

/**
 * The Layer-2 browser probe's *structured* findings — surfaced after the live
 * screenshots finish. Two things the screenshots alone can't convey:
 *   • Brand check — does the page's claimed platform match the domain it runs on?
 *   • Sensitive surfaces — which login / payment / transfer pages it reached and
 *     exactly what each one asks the buyer to hand over.
 */

const SURFACE_LABEL: Record<string, string> = {
  login_required: "Login",
  payment_required: "Payment",
  ticket_transfer_claim: "Ticket transfer",
  off_platform_payment: "Off-platform payment",
  event_listing: "Listing",
  quantity_modal: "Quantity",
  ticket_detail: "Ticket detail",
  blocked_or_captcha: "Blocked / captcha",
  error_page: "Error page",
};

function surfaceLabel(state: string): string {
  return SURFACE_LABEL[state] ?? state.replace(/_/g, " ");
}

type SurfaceTone = "danger" | "warn" | "muted";

/**
 * Classify a surface by what it ACTUALLY asks the buyer to fill in
 * (``requested_inputs``) — NOT by the page's ``action_types``. A checkout step's
 * action_types say "payment" even when this particular form only collects a name
 * + address + email, so mixing the two mislabels a contact form as "Payment".
 * action_types / page_state are only a fallback when no concrete fields were seen.
 */
function classifySurface(s: SensitiveSurface): { label: string; tone: SurfaceTone } {
  const inputs = s.requested_inputs.join(" ").toLowerCase();
  const hasIn = (...kws: string[]) => kws.some((k) => inputs.includes(k));

  // Primary: the real fields the form requests.
  if (hasIn("password")) return { label: "Login", tone: "danger" };
  if (hasIn("card", "cvv", "credit", "card_number", "payment", "iban"))
    return { label: "Payment", tone: "danger" };
  if (hasIn("otp", "verification")) return { label: "Verification code", tone: "danger" };
  if (hasIn("transfer")) return { label: "Ticket transfer", tone: "danger" };
  if (hasIn("name", "email", "phone", "mobile", "address", "zip", "post", "city"))
    return { label: "Personal details", tone: "warn" };

  // Fallback: no concrete inputs captured — describe the page's declared role.
  const actions = s.action_types.join(" ").toLowerCase();
  if (actions.includes("password") || s.page_state === "login_required")
    return { label: "Login", tone: "danger" };
  if (actions.includes("payment") || s.page_state === "payment_required")
    return { label: "Payment page", tone: "warn" };
  return { label: surfaceLabel(s.page_state), tone: "muted" };
}

function prettyInputs(inputs: string[]): string {
  return inputs.map((i) => i.replace(/_/g, " ")).join(", ");
}

interface BrandView {
  tone: "good" | "bad" | "neutral";
  text: string;
}

/**
 * The brand check is only meaningful when there is a RECOGNIZED brand/marketplace
 * to verify against — a trusted whitelisted domain, or a page claiming a known
 * brand (which the backend resolved to True=on its official domain or
 * False=impersonation). A site that merely claims its own unknown name (e.g.
 * "eTicketing.co" on eticketing.co) has nothing to check, so we render no brand
 * row at all and let the sensitive surfaces + OSINT reputation speak instead.
 */
function describeBrand(brand: BrandCheck): BrandView | null {
  if (brand.matches === false) {
    return {
      tone: "bad",
      text:
        brand.mismatch_reason ||
        `Claims ${brand.claimed_platform ?? "a known brand"}, but the live domain (${
          brand.domain ?? "?"
        }) doesn't match`,
    };
  }
  if (brand.trusted) {
    return { tone: "good", text: `Trusted marketplace · ${brand.domain ?? ""}` };
  }
  if (brand.matches === true) {
    return { tone: "good", text: `Brand matches its domain · ${brand.domain ?? ""}` };
  }
  // No recognized brand to verify (matches === null, untrusted domain) → no row.
  return null;
}

export function BrowserFindings({
  brand,
  surfaces,
  variant = "card",
}: {
  brand: BrandCheck | null;
  surfaces: SensitiveSurface[];
  /** "card" = standalone panel (report); "frame" = flush footer inside the
   *  live security viewport, sharing its clay frame. */
  variant?: "card" | "frame";
}) {
  const brandView = brand ? describeBrand(brand) : null;
  const hasOffPlatform = !!brand?.off_platform_payment;
  // Nothing verifiable to show (unknown site, no off-platform flag, no surfaces).
  if (!brandView && !hasOffPlatform && surfaces.length === 0) return null;

  return (
    <div className={`bfind${variant === "frame" ? " bfind--frame" : ""}`}>
      <div className="bfind-title">
        {variant === "frame" ? "Findings" : "Browser findings"}
      </div>

      {brandView && (
        <div className={`bfind-row bfind-row--${brandView.tone}`}>
          <span className="bfind-key">Brand check</span>
          <span className="bfind-val">{brandView.text}</span>
        </div>
      )}

      {brand?.off_platform_payment && (
        <div className="bfind-row bfind-row--bad">
          <span className="bfind-key">Off-platform</span>
          <span className="bfind-val">
            Requests payment outside the platform (Zelle / Venmo / crypto / gift card)
          </span>
        </div>
      )}

      {surfaces.length > 0 && (
        <div className="bfind-surfaces">
          <span className="bfind-key">Sensitive surfaces</span>
          <ul className="bfind-list">
            {surfaces.map((s, i) => {
              const tag = classifySurface(s);
              return (
                <li key={`${s.page_state}-${i}`} className="bfind-surface">
                  <span
                    className={`bfind-tag bfind-tag--${tag.tone}`}
                    title={
                      s.reached
                        ? "Agent navigated onto this page"
                        : "Link observed, not entered"
                    }
                  >
                    {tag.label}
                  </span>
                  <span className="bfind-asks">
                    {s.requested_inputs.length
                      ? `asks for: ${prettyInputs(s.requested_inputs)}`
                      : s.action_types.length
                        ? `exposes: ${prettyInputs(s.action_types)}`
                        : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
