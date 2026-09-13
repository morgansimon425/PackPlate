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
FIELDNAMES = ["prompt_id", "category", "source", "base_starters", "new_modules", "model", "model_id", "provider", "web", "response", "verdict", "notes", "seconds", "error"]
MANIFEST_FIELDS = ["id", "name", "source", "base_starters", "new_modules", "runnable"]

# proj1b: three cloud LLMs + one local (Ollama-class). See config.example.json.
EXPECTED_MODELS = 4


def prompt_order(prompt_set="enriched"):
    """Return the selected prompt set in file order."""
    ordered = []
    fname = "enriched_prompts.json" if prompt_set == "enriched" else "starter_prompts.json"
    fp = ROOT / fname
    if fp.exists():
        for p in json.loads(fp.read_text(encoding="utf-8")):
            ordered.append({"id": p["id"], "category": p.get("category", "enriched" if prompt_set == "enriched" else "starter"),
                            "source": p.get("source", "starter"),
                            "base_starters": json.dumps(p.get("base_starters", []), separators=(",", ":")),
                            "new_modules": p.get("new_modules", "")})
    return ordered


def write_manifest():
    """Write provenance from prompt definitions, independent of model output."""
    prompts = json.loads((ROOT / "enriched_prompts.json").read_text(encoding="utf-8"))
    rows = []
    for p in prompts:
        rows.append({
            "id": p["id"], "name": p["name"], "source": p["source"],
            "base_starters": json.dumps(p.get("base_starters", []), separators=(",", ":")),
            "new_modules": p.get("new_modules", ""), "runnable": str(p.get("runnable", True)).lower(),
        })
    out = ROOT / "prompt_provenance.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    counts = {source: sum(1 for p in prompts if p["source"] == source)
              for source in ("starter", "enriched", "combination")}
    print(f"prompt provenance: {counts['starter']} starter, {counts['enriched']} enriched, "
          f"{counts['combination']} combination")
    print(f"wrote {out} ({len(rows)} prompts)")


def main():
    write_manifest()
    csv_files = sorted(RESULTS_DIR.glob("*.csv")) if RESULTS_DIR.exists() else []
    if not csv_files:
        raise SystemExit("No results_prompts/<model>.csv found. Run run_prompts.py first.")

    by_model = {}
    for f in csv_files:
        model = f.stem
        with open(f, newline="", encoding="utf-8") as fh:
            by_model[model] = {r["prompt_id"]: r for r in csv.DictReader(fh)}

    models = sorted(by_model.keys())
    result_ids = {pid for rows_for_model in by_model.values() for pid in rows_for_model}
    prompt_set = "enriched" if any(pid.startswith("P") for pid in result_ids) else "starters"
    prompts = prompt_order(prompt_set)

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
                    "base_starters": p["base_starters"],
                    "new_modules": p["new_modules"],
                    "model": m,
                    "model_id": r.get("model_id", ""),
                    "provider": r.get("provider", ""),
                    "web": r.get("web", ""),
                    "response": r.get("response", ""),
                    "verdict": r.get("verdict", ""),
                    "notes": r.get("notes", ""),
                    "seconds": r.get("seconds", ""),
                    "error": r.get("error", ""),
                })
            else:
                rows.append({
                    "prompt_id": pid,
                    "category": p["category"],
                    "source": p["source"],
                    "base_starters": p["base_starters"],
                    "new_modules": p["new_modules"],
                    "model": m,
                    "model_id": "",
                    "provider": "",
                    "web": "",
                    "response": "_not run_",
                    "verdict": "",
                    "notes": "",
                    "seconds": "",
                    "error": "",
                })

    out = ROOT / "all_models.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"prompt set: {prompt_set}")
    print(f"models found: {', '.join(models)}")
    ids = {m: next((r["model_id"] for r in rows if r["model"] == m and r["model_id"]), "") for m in models}
    unknown = [m for m, i in ids.items() if not i]
    for m, i in ids.items():
        if i:
            print(f"  {m}: {i}")
    if unknown:
        print(f"  NO model_id recorded for: {', '.join(unknown)} - these rows predate the "
              f"model_id column. Fill it in by hand or re-run with overwrite.")
    print(f"wrote {out} ({len(rows)} rows = {len(prompts)} prompts x {len(models)} model(s))")
    if len(models) < EXPECTED_MODELS:
        print(f"NOTE: only {len(models)}/{EXPECTED_MODELS} models have results in {RESULTS_DIR} "
              f"- rerun once everyone's committed theirs.")
    not_run = sum(1 for r in rows if r["response"] == "_not run_")
    if not_run:
        print(f"NOTE: {not_run} (prompt, model) pair(s) have no result at all.")

    # D1's two-model rule is a human judgment call on the market-survey rows,
    # but flag the raw material for it here so it isn't forgotten.
    survey_rows = [r for r in rows if r["prompt_id"] == "P1"
                   and r["response"] not in ("", "_not run_")]
    if survey_rows:
        print(f"\nD1 reminder: {len(survey_rows)} P1 market-survey response(s) to cross-check. "
              f"A rival counts only if two models name it, or one gives a live URL.")
        blind = sorted({r["model"] for r in survey_rows if r["web"] == "unavailable"})
        if blind:
            print(f"  Answered WITHOUT web access (recall, not evidence): {', '.join(blind)}. "
                  f"A URL from these needs checking by hand before it counts.")

    red_team_rows = [r for r in rows if r["prompt_id"] == "P6" and r["response"] not in ("", "_not run_")]
    if red_team_rows:
        print(f"P6 red-team reminder: {len(red_team_rows)} response(s) to include in D5.")


if __name__ == "__main__":
    main()
