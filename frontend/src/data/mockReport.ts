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
  },
  overallScore: 18,
  verdict: "danger",
  recommendation:
    "Strongly advise against purchase — counterfeit site combined with illegal markup.",
};
