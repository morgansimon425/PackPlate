"""Run the configured prompt set through one model and log one row per prompt
to
results_prompts/<your model>.csv -- with a `category` column ("starter" or
"enriched") and provenance columns so the six team prompts stay distinguishable.

A prompt marked "runnable": false is skipped and logged as such -- never faked.

Ported from CSC_510_Proj3/se26f/proj1a/prompts/run_prompts.py. Three
differences, all flagged in-place below:
  * BLANK CHECK -- proj1b's prompts ship with <<FILL IN: ...>> placeholders.
    A prompt with any left unfilled is refused, not sent. See check_blanks.
  * `chain` config flag -- proj1a always passed a session, which made every
    non-(cli+claude) config error out on every prompt. Set "chain": false
    for codex / agy / ollama and they run unchained instead.
  * WEB ACCESS, on by default. proj1b's prompt 1 wants an evidence URL per
    rival and prompt 7 wants FOUND/NOT-FOUND sources, neither of which a
    tool-less model can honestly produce. A prompt can opt out with
    "web_access": false. Not every model can honour it (the local one
    can't at all), so the `web` column records what each row actually had.
    * No repo to explore, so nothing sets file_access yet. The machinery is
    still here if we want it later.

Usage: python run_prompts.py
"""

import csv
import json
import re
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))  # providers.py lives one level up, in proj_1b/

from providers import call_model, web_capability

RESULTS_DIR = ROOT / "results_prompts"
FIELDNAMES = ["prompt_id", "category", "source", "base_starters", "new_modules", "model", "web", "response", "verdict", "seconds", "error"]

# proj1b prompts get web access unless they say otherwise -- the opposite
# of proj1a's default. See providers.call_cli's TOOL POSTURE note.
WEB_DEFAULT = True

# Matches <<FILL IN: whatever>> -- the placeholder convention in
# starter_prompts.json. Deliberately distinct from the assignment's own
# <angle bracket> notation so it is unambiguously greppable.
BLANK_RE = re.compile(r"<<FILL IN:.*?>>", re.DOTALL)

# Matches <<FROM: P1>> -- a reference to another prompt's response, pasted in
# automatically just before this prompt is sent. Deliberately NOT matched by
# BLANK_RE: an unresolved reference is not a human blank, it just means the
# prompt it depends on has not run yet.
FROM_RE = re.compile(r"<<FROM:\s*([A-Za-z0-9_]+)\s*>>")


def resolve_refs(text, responses):
    """Replace every <<FROM: X>> with prompt X's response.

    Returns (resolved_text, missing). A prompt with anything missing is logged
    PENDING and never sent -- sending it with an empty paste would produce a
    confident answer to a question we did not actually ask, which is the same
    failure shape the blank check exists to prevent.
    """
    missing = []

    def sub(match):
        pid = match.group(1)
        resp = responses.get(pid, "")
        if not resp.strip():
            missing.append(pid)
            return match.group(0)
        return resp

    return FROM_RE.sub(sub, text), missing


def _normalize_prompt(prompt):
    """Give both prompt-file shapes the runner's internal `text` field."""
    normalized = dict(prompt)
    if "text" not in normalized:
        normalized["text"] = normalized.pop("prompt_text")
    normalized.setdefault("category", "starter")
    normalized.setdefault("source", "starter")
    normalized.setdefault("base_starters", [])
    normalized.setdefault("new_modules", "")
    normalized.setdefault("web_access", normalized.get("web", "on") == "on")
    return normalized


def _prompt_row_metadata(prompt, model_name):
    return {
        "prompt_id": prompt["id"],
        "category": prompt["category"],
        "source": prompt["source"],
        "base_starters": json.dumps(prompt.get("base_starters", []), separators=(",", ":")),
        "new_modules": prompt.get("new_modules", ""),
        "model": model_name,
    }


def check_blanks(prompts):
    """Refuse to run if any runnable prompt still has an unfilled blank.

    Without this the harness happily sends a model the literal text
    "<<FILL IN: our one-paragraph product description>>", gets a confident
    answer about nothing, and logs it as a real result -- the same failure
    shape as proj1a's argv-truncation bug, where a row looks valid and
    isn't. Fail loudly at the start instead.
    """
    offenders = []
    for p in prompts:
        if not p.get("runnable", True):
            continue
        blanks = BLANK_RE.findall(p["text"])
        if blanks:
            offenders.append((p["id"], blanks))
    if offenders:
        lines = ["Unfilled blanks -- nothing was sent to any model. Fill these in first:\n"]
        for pid, blanks in offenders:
            lines.append(f"  {pid}  ({len(blanks)} blank(s))")
            for b in blanks:
                flat = " ".join(b.split())
                lines.append(f"      {flat[:150]}")
        lines.append("\n(Or set \"runnable\": false on a prompt you are deliberately not running.)")
        raise SystemExit("\n".join(lines))


def _cfg_supports_file_access(cfg):
    """Mirrors providers.py's own constraint exactly (call_cli / call_model):
    file_access is only wired up for provider "cli" with cli "claude"."""
    return cfg.get("provider") == "cli" and cfg.get("cli") == "claude"


def _cfg_supports_chaining(cfg):
    """Same constraint, for conversation chaining. `chain` in config.json
    can turn it off; it cannot turn it on for a config providers.py won't
    chain anyway."""
    return cfg.get("chain", True) and _cfg_supports_file_access(cfg)


def load_prompts(cfg):
    """Return the configured run set, defaulting to the six enriched prompts."""
    starter = json.loads((ROOT / "starter_prompts.json").read_text(encoding="utf-8"))
    enriched_fp = ROOT / "enriched_prompts.json"
    enriched = json.loads(enriched_fp.read_text(encoding="utf-8")) if enriched_fp.exists() else []
    prompt_set = cfg.get("prompt_set", "enriched")
    if prompt_set in ("starter", "starters", "raw_starters"):
        return [_normalize_prompt(p) for p in starter]
    if prompt_set != "enriched":
        raise SystemExit(f"Unknown prompt_set {prompt_set!r}; use \"enriched\" or \"raw_starters\".")
    return [_normalize_prompt(p) for p in enriched]


def main():
    cfg_path = ROOT.parent / "config.json"
    if not cfg_path.exists():
        raise SystemExit("Missing config.json. Copy config.example.json to config.json and edit it first.")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    model_name = cfg["name"]

    prompts = load_prompts(cfg)
    check_blanks(prompts)

    if _cfg_supports_chaining(cfg):
        # One conversation for the whole run. The first call names the
        # session, every later one resumes it (see providers.py), so each
        # prompt is answered with everything before it in context.
        session = {"id": str(uuid.uuid4()), "started": False}
        print(f"All prompts share one conversation (session {session['id'][:8]}...), "
              f"so each prompt sees the ones before it.")
    else:
        session = None
        why = "chain:false in config.json" if not cfg.get("chain", True) else \
              f"provider '{cfg['provider']}'/cli '{cfg.get('cli')}' cannot chain"
        print(f"Unchained run ({why}) -- each prompt is answered in isolation.")

    swaps = [(p["_replaced_by"], p["id"]) for p in prompts if p.get("_replaced_by")]
    for new, old in swaps:
        print(f"  {new} replaces {old}")
    print()

    RESULTS_DIR.mkdir(exist_ok=True)
    out_csv = RESULTS_DIR / f"{model_name}.csv"

    existing = {}
    if out_csv.exists() and not cfg.get("overwrite"):
        with open(out_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r.setdefault("category", "starter")
                r.setdefault("source", "starter")
                r.setdefault("base_starters", "[]")
                r.setdefault("new_modules", "")
                r.setdefault("web", "")  # backfill rows logged before this column existed
                if "PENDING" in r.get("verdict", ""):
                    continue  # a <<FROM:>> reference could not resolve last run -- retry it
                if not r.get("error") and (r.get("response") or "not runnable" in r.get("verdict", "")):
                    existing[r["prompt_id"]] = r

    rows = []
    # Responses keyed by prompt id, so a later prompt can paste an earlier one
    # in via <<FROM: X>>. Seeded from rows we already have, so a re-run can
    # still resolve references to prompts that are being skipped.
    responses = {pid: r.get("response", "") for pid, r in existing.items()}
    for p in prompts:
        if p["id"] in existing:
            print(f"skip {p['id']} (already have a result for {model_name})")
            rows.append(existing[p["id"]])
            continue

        if p.get("_replaced_by"):
            print(f"skip {p['id']} (replaced by {p['_replaced_by']})")
            row = _prompt_row_metadata(p, model_name)
            row.update({"web": "", "response": "", "verdict": f"N/A - replaced by {p['_replaced_by']}",
                        "seconds": "", "error": ""})
        elif not p.get("runnable", True):
            print(f"skip {p['id']} (marked not runnable - {p['source']})")
            row = _prompt_row_metadata(p, model_name)
            row.update({"web": "", "response": "", "verdict": "N/A - not runnable, see source",
                        "seconds": "", "error": ""})
        else:
            wants_web = p.get("web_access", WEB_DEFAULT)
            web = web_capability(cfg, wants_web)
            prompt_text, missing = resolve_refs(p["text"], responses)
            if missing:
                waiting = ", ".join(sorted(set(missing)))
                print(f"skip {p['id']} (waiting on {waiting})")
                row = _prompt_row_metadata(p, model_name)
                row.update({"web": "", "response": "", "verdict": f"PENDING - waiting on {waiting}",
                            "seconds": "", "error": ""})
                rows.append(row)
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                    writer.writeheader()
                    writer.writerows(rows)
                continue

            pasted = FROM_RE.findall(p["text"])
            mode = " [FILE ACCESS]" if p.get("file_access") else ""
            mode += f" [web: {web}]"
            if pasted:
                mode += f" [pasted in: {', '.join(pasted)}]"
            print(f"running {p['id']} ({p['category']}) on {model_name}{mode} ...")
            start = time.time()
            try:
                response = call_model(cfg, prompt_text, file_access=p.get("file_access", False),
                                      session=session, web_access=wants_web)
                error = ""
            except Exception as exc:  # noqa: BLE001
                response, error = "", str(exc)

            responses[p["id"]] = response

            row = _prompt_row_metadata(p, model_name)
            row.update({"web": web, "response": response, "verdict": "",
                        "seconds": round(time.time() - start, 1), "error": error})
            print(f"  -> {len(response)} chars back" + (f"  [ERROR: {error}]" if error else ""))

        rows.append(row)
        # rewrite after every prompt so a crash mid-run keeps what we have
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

    print(f"\nDone. {out_csv} has {len(rows)} row(s) "
          f"({sum(1 for r in rows if r['category'] == 'starter')} starter, "
          f"{sum(1 for r in rows if r['category'] == 'enriched')} enriched).")
    webs = {r["web"] for r in rows if r["web"]}
    pending = [r["prompt_id"] for r in rows if "PENDING" in r.get("verdict", "")]
    if pending:
        print(f"PENDING: {', '.join(pending)} did not run — a prompt they paste in "
              f"has no result yet. Re-run once it does.")
    if "unavailable" in webs:
        print("NOTE: at least one prompt asked for web access this model cannot provide "
              "(web=unavailable). Those answers are recall, not evidence -- say so in D5.")
    print("Read the responses, fill in the `verdict` column by hand (correct / wrong / hallucinated / partial),")
    print("commit this CSV, then once everyone's done: python build_all_models.py")


if __name__ == "__main__":
    main()
