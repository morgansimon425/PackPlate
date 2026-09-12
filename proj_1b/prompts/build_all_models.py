"""Combine everyone's results_prompts/<model>.csv into one long-format file:
one row per (prompt, model) pair, with the FULL response text -- the
"prompt x model -> verdict" table D5 asks for.

Ported from CSC_510_Proj3/se26f/proj1a/prompts/build_all_models.py, with
EXPECTED_MODELS at 4 (not 5) and a `web` column carried through -- see
providers.web_capability for what its values mean.

Usage: python build_all_models.py
Output: all_models.csv
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
RESULTS_DIR = ROOT / "results_prompts"
FIELDNAMES = ["prompt_id", "category", "source", "model", "web", "response", "verdict", "seconds", "error"]

# proj1b: three cloud LLMs + one local (Ollama-class). See config.example.json.
EXPECTED_MODELS = 4


def prompt_order():
    """Return [{"id", "category", "source"}, ...] across starter and enriched
    prompt files, in file order, including non-runnable ones."""
    ordered = []
    for fname in ("starter_prompts.json", "enriched_prompts.json"):
        fp = ROOT / fname
        if fp.exists():
            for p in json.loads(fp.read_text(encoding="utf-8")):
                ordered.append({"id": p["id"], "category": p.get("category", "starter"),
                                "source": p.get("source", "")})
    return ordered


def main():
    csv_files = sorted(RESULTS_DIR.glob("*.csv")) if RESULTS_DIR.exists() else []
    if not csv_files:
        raise SystemExit("No results_prompts/<model>.csv found. Run run_prompts.py first.")

    by_model = {}
    for f in csv_files:
        model = f.stem
        with open(f, newline="", encoding="utf-8") as fh:
            by_model[model] = {r["prompt_id"]: r for r in csv.DictReader(fh)}

    models = sorted(by_model.keys())
    prompts = prompt_order()

    rows = []
    for p in prompts:
        pid = p["id"]
        for m in models:
            r = by_model.get(m, {}).get(pid)
            if r:
                rows.append({
                    "prompt_id": pid,
                    "category": p["category"],
                    "source": p["source"],
                    "model": m,
                    "web": r.get("web", ""),
                    "response": r.get("response", ""),
                    "verdict": r.get("verdict", ""),
                    "seconds": r.get("seconds", ""),
                    "error": r.get("error", ""),
                })
            else:
                rows.append({
                    "prompt_id": pid,
                    "category": p["category"],
                    "source": p["source"],
                    "model": m,
                    "web": "",
                    "response": "_not run_",
                    "verdict": "",
                    "seconds": "",
                    "error": "",
                })

    out = ROOT / "all_models.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"models found: {', '.join(models)}")
    print(f"wrote {out} ({len(rows)} rows = {len(prompts)} prompts x {len(models)} model(s))")
    if len(models) < EXPECTED_MODELS:
        print(f"NOTE: only {len(models)}/{EXPECTED_MODELS} models have results in {RESULTS_DIR} "
              f"- rerun once everyone's committed theirs.")
    not_run = sum(1 for r in rows if r["response"] == "_not run_")
    if not_run:
        print(f"NOTE: {not_run} (prompt, model) pair(s) have no result at all.")

    # D1's two-model rule is a human judgment call on the market-survey rows,
    # but flag the raw material for it here so it isn't forgotten.
    survey_rows = [r for r in rows if r["prompt_id"].startswith("starter_01")
                   and r["response"] not in ("", "_not run_")]
    if survey_rows:
        print(f"\nD1 reminder: {len(survey_rows)} market-survey response(s) to cross-check. "
              f"A rival counts only if two models name it, or one gives a live URL.")
        blind = sorted({r["model"] for r in survey_rows if r["web"] == "unavailable"})
        if blind:
            print(f"  Answered WITHOUT web access (recall, not evidence): {', '.join(blind)}. "
                  f"A URL from these needs checking by hand before it counts.")


if __name__ == "__main__":
    main()
