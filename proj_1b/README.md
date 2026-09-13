# proj_1b

Runs the Project 1b prompts through an LLM and saves the answers to a CSV.
Run it once per model to compare how different models answer.

Assignment: https://github.com/txt/se26f/blob/main/docs/submit/1/proj1b.md

## Pick a model

```
cp config.example.json config.json
```

`config.example.json` has a block for each of the four models. Copy one to
the top of `config.json` and follow the setup notes inside that block.
`config.json` is gitignored.

The Claude, Codex, and Antigravity blocks authenticate via their CLI's own
login command (see `_setup` in each block) — no environment variable needed.
The Gemini API block (and the metered alternatives at the bottom of the
file) instead read a key from an environment variable named in
`api_key_env`, set outside `config.json`. How to set one depends on your
shell, e.g. for `GOOGLE_API_KEY`:

```
# Windows PowerShell
$env:GOOGLE_API_KEY = "your-key-here"

# macOS / Linux (bash/zsh)
export GOOGLE_API_KEY=your-key-here
```

The default `prompt_set` is `enriched`, which runs the six team prompts P1-P6
and excludes the superseded and dropped starters. Set `prompt_set` to
`raw_starters` to run the original 12 prompts instead.

## Run the prompts

```
cd prompts
python run_prompts.py
```

Answers are saved to `results_prompts/<model name>.csv`. Each row includes the
prompt source (`starter`, `enriched`, or `combination`), its base starter
numbers, any team-invented modules, and which model actually answered
(`model_id`, `provider`) — set `"model"` explicitly in `config.json`.

To run another model, change `config.json` and run it again. Each model
writes its own file.

## Mark the answers

Open the CSV and fill in the `verdict` column for each row: correct, wrong,
hallucinated, or partial. Use `notes` for the evidence behind that verdict —
what was wrong, what you checked, what you couldn't verify.

## Merge the results

```
python build_all_models.py
```

Writes `all_models.csv`, one row per prompt per model, with the same provenance
columns. It also writes `prompt_provenance.csv`, a prompt-definition manifest
independent of model output.

## Files

```
providers.py             connects to whichever model you configured
config.example.json      copy this to config.json
prompts/
  starter_prompts.json   the 12 prompts from the assignment (unchanged)
  enriched_prompts.json  the six team-enriched prompts and provenance metadata
  prompt_provenance.csv  generated manifest for the enriched prompt set
  run_prompts.py         runs the prompts
  build_all_models.py    merges the results
  results_prompts/       one CSV per model
```

## If something looks off

**"Unfilled blanks" error.** The prompts have `<<FILL IN: ...>>` placeholders
where our project details go. The script stops and lists which ones are
still empty instead of sending them to a model.

**Some rows say N/A.** Prompts marked `"runnable": false` are skipped on
purpose. P2 is the only one — its gap sentence is written after reading P1's
results, then it runs on a second pass.

**Some rows say PENDING.** A prompt containing `<<FROM: P1>>` gets P1's answer
pasted in automatically before it is sent. If that answer doesn't exist yet,
the prompt is logged PENDING and retried next run rather than being sent with
a gap in it. P6 uses this to pull in P1, P3 and P4, so it runs in the same
pass as everything else.

**The `web` column.** Shows whether the model could search the web. The local
model can't, so its answers come from memory and may be made up.
