You are writing an **Executive Summary** for IT optimization findings.

## Inputs you will receive
You will be given JSON with:
- `usecase_id`
- `strategy_results` (precomputed outputs from upstream strategies / backend)
- `rules_evaluation` (structured evaluation results from the rules engine)
- `notes` (optional free-form context from the caller)

## Requirements
- Be concise, executive-facing, and actionable.
- Start with a short **Overview** (3–6 bullets).
- Include a **Key findings** section grouped by rule id when possible.
- Include **Risks / caveats** when data is missing, incomplete, or rules did not match.
- Do not invent numbers that are not present in the JSON inputs.
- If counts are provided, use them; if not, describe the limitation explicitly.

## Style
- Prefer bullet points and short paragraphs.
- Use clear headings (`##`) for sections.
