"""Run every prompt in starter_prompts.json (the 12 official proj1b prompts)
AND enriched_prompts.json (our own, kept in a separate file on purpose)
through your configured model (config.json), and log one row per prompt to
results_prompts/<your model>.csv -- with a `category` column ("starter" or
"enriched") so the two stay clearly distinguishable even though they're
logged together. Columns match what D5 needs: prompt id, category, source,
your model's full response, and a blank `verdict` column for a human to
fill in after reading it (see build_all_models.py).

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
FIELDNAMES = ["prompt_id", "category", "source", "model", "web", "response", "verdict", "seconds", "error"]

# proj1b prompts get web access unless they say otherwise -- the opposite
# of proj1a's default. See providers.call_cli's TOOL POSTURE note.
WEB_DEFAULT = True

# Matches <<FILL IN: whatever>> -- the placeholder convention in
# starter_prompts.json. Deliberately distinct from the assignment's own
# <angle bracket> notation so it is unambiguously greppable.
BLANK_RE = re.compile(r"<<FILL IN:.*?>>", re.DOTALL)


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
    """Return the prompts in execution order, applying enriched-over-starter
    replacements -- but ONLY for a config that can actually run the
    replacement (see _cfg_supports_file_access). Every other model gets the
    original starter prompt in its own slot, unreplaced, so it answers what
    it can actually answer instead of inheriting a swap it can't honour.

    An enriched prompt with "replaces": "<starter id>" takes that starter's
    POSITION in the run, which is what makes replacement useful: put the
    replacement on starter #1 and it runs first, so with one shared
    conversation everything after it inherits whatever it read.

    The replaced starter is not dropped -- it stays in the list carrying a
    _replaced_by marker, so it is logged as an explicit N/A row. That keeps
    our CSV aligned with teammates who ran the original prompt, instead of
    the row silently vanishing from the merged table.
    """
    starter = json.loads((ROOT / "starter_prompts.json").read_text(encoding="utf-8"))
    enriched_fp = ROOT / "enriched_prompts.json"
    enriched = json.loads(enriched_fp.read_text(encoding="utf-8")) if enriched_fp.exists() else []

    starter_ids = {p["id"] for p in starter}
    replacements = {}
    for p in enriched:
        target = p.get("replaces")
        if not target:
            continue
        if target not in starter_ids:
            raise SystemExit(f"{p['id']} has \"replaces\": \"{target}\", which is not a starter prompt id. "
                             f"Valid ids: {', '.join(sorted(starter_ids))}")
        if target in replacements:
            raise SystemExit(f"Both {replacements[target]['id']} and {p['id']} claim to replace {target}. "
                             f"Only one enriched prompt may replace a given starter prompt.")
        replacements[target] = p

    can_replace = _cfg_supports_file_access(cfg)

    ordered = []
    for p in starter:
        replacement = replacements.get(p["id"])
        if replacement and can_replace:
            ordered.append({**p, "_replaced_by": replacement["id"]})
            ordered.append(replacement)
        else:
            # either nothing wants to replace this one, or something does but
            # this model can't run it (e.g. no file_access support) -- run
            # the original starter prompt normally either way.
            ordered.append(p)
    # enriched prompts that don't replace anything (or couldn't, for this
    # model) just run after the starters, unless they need something this
    # config can't provide -- then skip them outright rather than error.
    for p in enriched:
        if p.get("replaces") and not can_replace:
            continue  # not attempted -- it would just error
        if not p.get("replaces"):
            ordered.append(p)
        elif can_replace:
            pass  # already placed in the starter's slot above
    return ordered


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
                r.setdefault("web", "")  # backfill rows logged before this column existed
                if not r.get("error") and (r.get("response") or "not runnable" in r.get("verdict", "")):
                    existing[r["prompt_id"]] = r

    rows = []
    for p in prompts:
        if p["id"] in existing:
            print(f"skip {p['id']} (already have a result for {model_name})")
            rows.append(existing[p["id"]])
            continue

        if p.get("_replaced_by"):
            print(f"skip {p['id']} (replaced by {p['_replaced_by']})")
            row = {
                "prompt_id": p["id"], "category": p["category"], "source": p["source"],
                "model": model_name, "web": "", "response": "",
                "verdict": f"N/A - replaced by {p['_replaced_by']}",
                "seconds": "", "error": "",
            }
        elif not p.get("runnable", True):
            print(f"skip {p['id']} (marked not runnable - {p['source']})")
            row = {
                "prompt_id": p["id"], "category": p["category"], "source": p["source"],
                "model": model_name, "web": "", "response": "",
                "verdict": "N/A - not runnable, see source",
                "seconds": "", "error": "",
            }
        else:
            wants_web = p.get("web_access", WEB_DEFAULT)
            web = web_capability(cfg, wants_web)
            mode = " [FILE ACCESS]" if p.get("file_access") else ""
            mode += f" [web: {web}]"
            print(f"running {p['id']} ({p['category']}) on {model_name}{mode} ...")
            start = time.time()
            try:
                response = call_model(cfg, p["text"], file_access=p.get("file_access", False),
                                      session=session, web_access=wants_web)
                error = ""
            except Exception as exc:  # noqa: BLE001
                response, error = "", str(exc)

            row = {
                "prompt_id": p["id"], "category": p["category"], "source": p["source"], "model": model_name,
                "web": web,
                "response": response, "verdict": "", "seconds": round(time.time() - start, 1),
                "error": error,
            }
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
    if "unavailable" in webs:
        print("NOTE: at least one prompt asked for web access this model cannot provide "
              "(web=unavailable). Those answers are recall, not evidence -- say so in D5.")
    print("Read the responses, fill in the `verdict` column by hand (correct / wrong / hallucinated / partial),")
    print("commit this CSV, then once everyone's done: python build_all_models.py")


if __name__ == "__main__":
    main()
