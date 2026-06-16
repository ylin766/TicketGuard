const CLOUD_RUN_API_URL = "https://ticketguard-backend-1086335517426.us-central1.run.app";
const OLD_RAILWAY_API_URL = "https://ticketguard-production.up.railway.app";

export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_URL?.trim();
  if (!configured || configured === OLD_RAILWAY_API_URL) {
    return CLOUD_RUN_API_URL;
  }
  return configured.replace(/\/$/, "");
}
