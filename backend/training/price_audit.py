"""Price agent: judge + AuditFn for the GEPA loop (no ground truth).

The price agent has no labelled answer — there is no "correct" verdict for a
listing's fairness. So its reward is purely an LLM judge over the *quality* of
the price assessment, plus the objective tool-success rate. This mirrors the
security path but swaps ground-truth correctness for judge-only scoring.

Two evolvable prompt components (both live in ``features.price.analysis``):
  * ``price_extract_prompt`` — vision extraction of the buyer's ticket
  * ``price_eval_prompt``     — the market-grounded fairness verdict

Judge rubrics (phoenix.evals, enum-labelled → 0..1):
  * ``price_grounding``   — is the verdict supported by the market stats given,
                            with no invented prices? (anti-hallucination)
  * ``price_consistency`` — does the verdict label agree with the percentile
                            band (e.g. low percentile -> good_deal)?

A price "example" needs cached inputs — a screenshot and scraped market listings
— since the verdict can't be produced from a URL alone. The AuditFn takes a
``snapshot_provider`` that yields those per URL, keeping the optimizer offline
and reproducible (no live scraping during training).
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Named GEPA components for the price agent (parallel to OSINT_COMPONENT).
PRICE_EXTRACT_COMPONENT = "price_extract_prompt"
PRICE_EVAL_COMPONENT = "price_eval_prompt"

# Judge label -> reward, same convention as observability.judge.
PRICE_REASONABLENESS_CHOICES: dict[str, float] = {
    "sound": 1.0,
    "partially_sound": 0.5,
    "unsound": 0.0,
}

_REASONABLENESS_TEMPLATE = """\
You are auditing the QUALITY of a ticket price-fairness assessment. There is no
ground-truth "correct" verdict — judge only whether the assessment is a *sound,
complete, well-reasoned* piece of buyer advice given the data it was shown. Do
NOT decide whether the price is actually fair yourself.

Buyer's ticket (JSON): {{user}}
Market statistics it was given (JSON): {{stats}}
Assessment produced: {{analysis}}

Grade STRICTLY against these three requirements:
  (1) GROUNDING — it explicitly cites the concrete market figures it was given
      (e.g. the median/average price, the percentile, and/or the listing count)
      and invents NO numbers that were not provided.
  (2) CLEAR VERDICT — it states an unambiguous fairness conclusion (e.g. good
      deal / fair / overpriced) that follows logically from those figures.
  (3) ACTIONABLE ADVICE — it gives at least one specific, useful next step for
      the buyer (e.g. how much could be saved, a cheaper option, what to do).

Respond:
- "sound" ONLY if ALL THREE requirements are clearly met.
- "partially_sound" if it has a clear verdict but is missing grounding in the
  given figures OR missing concrete actionable advice (i.e. one requirement
  unmet, or met only weakly/vaguely).
- "unsound" if it is a bare verdict with no grounding and no advice, invents
  figures, contradicts itself, or is otherwise unhelpful."""

_PRICE_EVALUATOR_SPECS = (
    ("price_reasonableness", _REASONABLENESS_TEMPLATE, PRICE_REASONABLENESS_CHOICES),
)

# A snapshot provider maps a URL -> (image_bytes, listings) so analyze() can run
# offline against cached market data instead of live-scraping during training.
SnapshotProvider = Callable[[str], tuple[bytes | None, list[dict]]]


def build_price_evaluators(llm=None) -> list:
    """Create the price judge evaluators via phoenix.evals. ``[]`` when the
    library or judge LLM is unavailable (caller then scores on tool-success
    only)."""
    from ..observability.judge import get_judge_llm

    llm = llm or get_judge_llm()
    if llm is None:
        return []
    try:
        from phoenix.evals import create_classifier
    except Exception as exc:  # noqa: BLE001
        logger.warning("[price-judge] phoenix.evals unavailable: %s", exc)
        return []

    evaluators = []
    for name, template, choices in _PRICE_EVALUATOR_SPECS:
        try:
            evaluators.append(
                create_classifier(name=name, prompt_template=template, llm=llm, choices=choices)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[price-judge] failed to build %s: %s", name, exc)
    return evaluators


def price_snapshot(audit: dict) -> dict:
    """Build the judging input for the price evaluators from an audit result."""
    return {
        "user": audit.get("user_listing", {}),
        "stats": audit.get("stats", {}),
        "analysis": audit.get("analysis", {}),
    }


def judge_price_audit(audit: dict, evaluators: list | None = None) -> dict[str, dict]:
    """Run the price judge over one audit; returns ``{dim: {score,label,explanation}}``.
    Best-effort: ``{}`` when judging is unavailable, skips any failing dimension."""
    evaluators = evaluators if evaluators is not None else build_price_evaluators()
    if not evaluators:
        return {}
    snapshot = price_snapshot(audit)
    out: dict[str, dict] = {}
    for evaluator in evaluators:
        name = getattr(evaluator, "name", "eval")
        try:
            scores = evaluator.evaluate(snapshot)
            if scores:
                s = scores[0]
                out[name] = {
                    "score": getattr(s, "score", None),
                    "label": getattr(s, "label", None),
                    "explanation": getattr(s, "explanation", None),
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("[price-judge] %s failed: %s", name, exc)
    return out


def assemble_price_audit(url: str, result: dict, *, tool_calls: int, tool_successes: int) -> dict:
    """Shape an ``analyze()`` result into the audit dict the metric consumes.

    Pure: rearranges fields and attaches tool stats under ``agent_audit.stats``
    where ``metric.tool_success_rate`` reads them."""
    return {
        "url": url,
        "user_listing": result.get("user_listing", {}),
        "stats": result.get("stats", {}),
        "analysis": result.get("analysis", {}),
        "agent_audit": {
            "stats": {
                "tool_calls": tool_calls,
                "tool_successes": tool_successes,
                "tool_failures": max(0, tool_calls - tool_successes),
            },
        },
    }


def make_price_audit_fn(
    snapshot_provider: SnapshotProvider,
    buyer_provider: Callable[[str], dict] | None = None,
):
    """Build the price ``AuditFn`` for the training runner.

    The returned coroutine runs ``analyze()`` for ``url`` using the candidate's
    extract/eval prompts over the cached snapshot, then returns the audit dict.

    ``buyer_provider`` optionally supplies the buyer's ticket (section/price) per
    url — used by the offline cached dataset to turn each seat into a distinct
    buyer scenario without needing a screenshot. When given, vision extraction
    is skipped. Never raises: a failure yields an empty-analysis audit so the
    runner can still score it.
    """
    async def price_audit_fn(url: str, candidate: dict[str, str]) -> dict:
        try:
            from ..features.price import analysis as price_analysis
        except Exception as exc:  # noqa: BLE001
            logger.warning("[price-audit] analysis import failed: %s", exc)
            return assemble_price_audit(url, {}, tool_calls=0, tool_successes=0)

        image_bytes, listings = snapshot_provider(url)
        # A scrape that returned listings counts as one successful "tool" use;
        # an empty scrape is a failure (no usable market data).
        tool_calls = 1
        tool_successes = 1 if listings else 0

        buyer = buyer_provider(url) if buyer_provider is not None else None
        # NOTE: extraction is NOT trained — these offline scenarios inject the
        # buyer ticket directly (vision extraction needs a real screenshot,
        # which we don't have offline). Only price_eval_prompt is optimized.
        eval_prompt = candidate.get(PRICE_EVAL_COMPONENT)
        try:
            user = buyer if buyer is not None else {}
            # analyze() computes market stats + applies FX normalization; we then
            # override the verdict with the candidate eval prompt (the component
            # under optimization).
            result = price_analysis.analyze(image_bytes, url, listings, user_listing=user or None)
            if eval_prompt and result.get("stats"):
                verdict = price_analysis.evaluate(
                    result.get("user_listing", {}), result["stats"],
                    result.get("recommendations", []), prompt=eval_prompt,
                )
                if verdict:
                    result["analysis"] = verdict
        except Exception as exc:  # noqa: BLE001 - one audit must not abort training
            logger.warning("[price-audit] analyze failed for %s: %s", url, exc)
            return assemble_price_audit(url, {}, tool_calls=tool_calls, tool_successes=0)

        return assemble_price_audit(
            url, result, tool_calls=tool_calls, tool_successes=tool_successes
        )

    return price_audit_fn


def price_seed_candidate() -> dict[str, str]:
    """The starting price prompt GEPA mutates.

    Only the *evaluation* prompt is optimized — extraction is excluded because
    it needs a real screenshot to exercise (not available in offline training).
    """
    from ..features.price.analysis import _EVAL_PROMPT

    return {PRICE_EVAL_COMPONENT: _EVAL_PROMPT}
