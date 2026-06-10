import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import "./UrlInputScreen.css";

interface UrlInputScreenProps {
  /** Called with the submitted URL + ticket quantity when the user starts an audit. */
  onAudit: (url: string, qty: number) => void;
  /** Whether an audit is currently running. */
  loading: boolean;
  /** Optional error message from a previous attempt. */
  error?: string | null;
}

/** Naive URL/host validation good enough for a paste-and-go field. */
function looksLikeUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  // Accept bare hosts ("stubhub.com/...") as well as full URLs.
  return /^(https?:\/\/)?[\w-]+(\.[\w-]+)+/.test(trimmed);
}

/**
 * Seat-precise demo URL prefilled in the input. Points at a specific World Cup
 * 2026 match (Spain vs. Cape Verde, Mercedes-Benz Stadium, Atlanta) on a smaller
 * resale marketplace whose domain reputation lands in the security grey zone
 * (verified score ≈87 < SAFE_MIN), so the audit escalates to the Layer-2
 * browser agent — while the page still exposes real seat-level prices that the
 * price flow compares against the StubHub/Ticketmaster reference market.
 */
const DEFAULT_URL =
  "https://www.boxofficeticketsales.com/6259536/fifa-world-cup-26-group-h-spain-vs-cape-verde-match-14-tickets-mon-6-15-2026-mercedes-benz-stadium";

export function UrlInputScreen({ onAudit, loading, error }: UrlInputScreenProps) {
  const [url, setUrl] = useState(DEFAULT_URL);
  const [qty, setQty] = useState(2);
  const [touched, setTouched] = useState(false);

  const valid = looksLikeUrl(url);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!valid || loading) return;
    onAudit(url.trim(), qty);
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setUrl(text.trim());
        setTouched(false);
      }
    } catch {
      // Clipboard blocked (no permission / insecure context) — silently ignore.
    }
  };

  return (
    <motion.div
      className="input-screen"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -24 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="brand-logo clay">
        <img
          className="brand-logo-img"
          src={`${import.meta.env.BASE_URL}logo.png`}
          alt="TicketGuard"
          width={240}
          height={240}
        />
      </div>

      <h1 className="input-title sr-only">TicketGuard</h1>

      <motion.form
        layoutId="data-carrier"
        layout
        className="input-card clay"
        onSubmit={handleSubmit}
        noValidate
        style={{ borderRadius: "var(--radius-lg)" }}
      >
        <div className={`neu-inset input-field${url ? " is-filled" : ""}`}>
          <span className="input-icon" aria-hidden="true">
            🔗
          </span>
          <input
            id="ticket-url"
            type="text"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            placeholder="Paste the listing link here"
            value={url}
            disabled={loading}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={() => setTouched(true)}
          />
          {url ? (
            <button
              type="button"
              className="field-action"
              onClick={() => setUrl("")}
              disabled={loading}
              aria-label="Clear input"
            >
              ✕
            </button>
          ) : (
            <button
              type="button"
              className="field-action"
              onClick={handlePaste}
              disabled={loading}
            >
              Paste
            </button>
          )}
        </div>

        <div className="qty-row">
          <span className="qty-label">How many tickets?</span>
          <div className="qty-options" role="group" aria-label="Ticket quantity">
            {[1, 2, 3, 4].map((n) => (
              <button
                key={n}
                type="button"
                className={`qty-chip neu-raised${qty === n ? " is-active" : ""}`}
                onClick={() => setQty(n)}
                disabled={loading}
                aria-pressed={qty === n}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        {touched && !valid ? (
          <p className="field-hint danger">That doesn’t look like a valid link.</p>
        ) : error ? (
          <p className="field-hint danger">{error}</p>
        ) : null}

        <button
          type="submit"
          className="audit-button neu-raised"
          disabled={loading || (touched && !valid)}
        >
          {loading ? (
            <span className="btn-loading">
              <span className="spinner" aria-hidden="true" />
              Auditing…
            </span>
          ) : (
            <>Audit this listing</>
          )}
        </button>

        <div className="example-row">
          <span className="example-label">No link?</span>
          <button
            type="button"
            className="example-chip"
            disabled={loading}
            onClick={() => {
              setUrl(DEFAULT_URL);
              setTouched(false);
            }}
          >
            Try a sample
          </button>
        </div>
      </motion.form>

      <ul className="trust-row">
        <li className="glass trust-chip">🌐 Site credibility</li>
        <li className="glass trust-chip">👁️ Sightline</li>
        <li className="glass trust-chip">💰 Fair price</li>
        <li className="glass trust-chip">⚖️ Legal cap</li>
      </ul>
    </motion.div>
  );
}
