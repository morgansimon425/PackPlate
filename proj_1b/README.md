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
numbers, and any team-invented modules.

To run another model, change `config.json` and run it again. Each model
writes its own file.

## Mark the answers

Open the CSV and fill in the `verdict` column for each row: correct, wrong,
hallucinated, or partial.

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
purpose. P2 and P6 need answers from earlier prompts first, so they run in a
second pass.

**The `web` column.** Shows whether the model could search the web. The local
model can't, so its answers come from memory and may be made up.
