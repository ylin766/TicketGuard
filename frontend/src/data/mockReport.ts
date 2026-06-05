import type { TicketReport } from "../types";

/**
 * Demo report used while the backend audit endpoint is still under
 * construction. Modeled on the sample output in the project README.
 */
export const mockReport: TicketReport = {
  url: "stubhub-tickets.com/listing/98234",
  match: "USA vs Mexico",
  venue: "MetLife Stadium",
  seat: { section: "114A", row: "3", seat: "7" },
  listingPrice: 3200,
  marketMedian: 1450,
  dimensions: {
    websiteCredibility: {
      score: 12,
      flags: ["NEW_DOMAIN", "OFF_PLATFORM_PAYMENT"],
      detail:
        "Domain registered 3 days ago; official domain is stubhub.com. Page requests off-platform Venmo payment.",
    },
    price: {
      score: 28,
      flags: ["SEVERE_MARKUP"],
      detail:
        "Market median is $1,450 (SeatGeek live P50). Listing markup is +120%, exceeding the NY legal cap by 310%.",
    },
    compliance: {
      score: 0,
      flags: ["EXCEEDS_RESALE_CAP"],
      detail:
        "NY Anti-Scalping Law Art. 25-AA caps resale at 10% over face value. This listing is potentially illegal.",
    },
    sightline: {
      score: 71,
      flags: [],
      detail:
        "No fixed obstructions detected; left-goal angle 92%. Note: if the site is counterfeit, seat info is unverifiable.",
    },
  },
  overallScore: 18,
  verdict: "danger",
  recommendation:
    "Strongly advise against purchase — counterfeit site combined with illegal markup.",
};
