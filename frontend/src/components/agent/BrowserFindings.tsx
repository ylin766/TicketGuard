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
 * Classify a surface by what it ACTUALLY asks for, not the model's page_state
 * guess — a step that only collects email + phone is contact info, not payment,
 * even if the page is on the way to checkout.
 */
function classifySurface(s: SensitiveSurface): { label: string; tone: SurfaceTone } {
  const txt = `${s.requested_inputs.join(" ")} ${s.action_types.join(" ")}`.toLowerCase();
  const has = (...kws: string[]) => kws.some((k) => txt.includes(k));

  if (has("password")) return { label: "Login", tone: "danger" };
  if (has("payment", "card", "billing", "cvv", "credit"))
    return { label: "Payment", tone: "danger" };
  if (has("otp", "verification", "verification_code"))
    return { label: "Verification code", tone: "danger" };
  if (has("transfer")) return { label: "Ticket transfer", tone: "danger" };
  if (has("email", "phone", "name", "zip", "address"))
    return { label: "Contact info", tone: "warn" };
  return { label: surfaceLabel(s.page_state), tone: "muted" };
}

function prettyInputs(inputs: string[]): string {
  return inputs.map((i) => i.replace(/_/g, " ")).join(", ");
}

interface BrandView {
  tone: "good" | "bad" | "neutral";
  text: string;
}

function describeBrand(brand: BrandCheck): BrandView {
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
  if (brand.claimed_platform) {
    return {
      tone: "neutral",
      text: `Claims ${brand.claimed_platform} on ${brand.domain ?? "this domain"}`,
    };
  }
  return {
    tone: "neutral",
    text: `Unrecognized site · ${brand.domain ?? "unknown domain"}`,
  };
}

export function BrowserFindings({
  brand,
  surfaces,
}: {
  brand: BrandCheck | null;
  surfaces: SensitiveSurface[];
}) {
  const hasBrand = !!(brand && (brand.claimed_platform || brand.domain));
  if (!hasBrand && surfaces.length === 0) return null;

  const brandView = brand ? describeBrand(brand) : null;

  return (
    <div className="bfind">
      <div className="bfind-title">Browser findings</div>

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
