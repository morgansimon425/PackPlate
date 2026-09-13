"""Minimal, dependency-free adapters for calling different LLM providers.

Ported from CSC_510_Proj3/se26f/proj1a/providers.py. Two changes:

  * CLI_CWD replaces SAFEBITES_DIR -- proj1b has no codebase to explore.
  * WEB ACCESS IS NOW A PER-PROMPT OPTION, and defaults ON. proj1a banned
    WebFetch/WebSearch on every CLI, which was right for proj1a (its
    prompts said "work only from this code", "use no outside knowledge of
    the product") but is wrong for proj1b, whose prompt 1 demands an
    evidence URL per rival and whose prompt 7 wants FOUND/NOT-FOUND
    sources. See call_cli and web_capability.

Add a new provider by writing a `call_<name>(cfg, prompt) -> str` function
and registering it in PROVIDERS. Every adapter reads its API key from an
environment variable (never store keys in config.json).
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


# The working directory CLI calls run in. Claude namespaces stored sessions
# by cwd, so every call in one conversation must share one -- that is the
# only reason this exists in proj1b (proj1a also used it to sandbox
# file_access reads to the SafeBites repo). Defaults to this folder, which
# always exists. Override with "project_dir" in config.json if you turn
# file_access on and want it scoped somewhere specific.
CLI_CWD = Path(__file__).resolve().parent


def web_capability(cfg, web_access):
    """What this config can ACTUALLY do about web access, as one of:

        "off"          the prompt didn't ask for it
        "on"           the model can search/fetch
        "unavailable"  the prompt asked, and this model cannot

    run_prompts.py logs this per row so D5 can state plainly which models
    were able to check their own claims. The distinction matters: a rival
    named by a model with "on" is a lookup, the same rival named by a model
    with "unavailable" is recall -- and only one of those is evidence.
    """
    if not web_access:
        return "off"
    provider = cfg["provider"]
    if provider == "cli":
        cli = cfg.get("cli")
        if cli == "claude":
            return "on"
        if cli == "codex":
            # `codex exec --search`. Verify on your machine with
            # `codex exec --help` before trusting a row from this path;
            # set "codex_search": false if the flag isn't there.
            return "on" if cfg.get("codex_search", True) else "unavailable"
        if cli == "agy":
            # --mode plan blocks tool use outright in headless mode, which
            # is also what keeps agy from writing files. Dropping it
            # re-enables everything, not just web, and the agy invocation
            # shape was never verified even in proj1a -- so this stays
            # honest rather than optimistic. For a web-capable Gemini, use
            # provider "google" with "grounding": true instead.
            return "unavailable"
    if provider == "google" and cfg.get("grounding"):
        return "on"
    # ollama and the raw API-key providers have no tools at all.
    return "unavailable"


def _resolve_cli(name):
    """subprocess.run() with a bare command name only finds real .exe files
    on Windows -- a Node-installed CLI like `codex` is actually a `.cmd`
    wrapper, which needs its extension resolved first (shutil.which does
    this correctly, cross-platform) or it fails with WinError 2 even
    though the same bare name works fine typed into a real shell."""
    resolved = shutil.which(name)
    if not resolved:
        fallback_dirs = [
            Path.home() / ".gemini" / "bin",
            Path.home() / "AppData" / "Local" / "agy" / "bin",
            Path.home() / ".local" / "bin",
        ]
        for fb in fallback_dirs:
            candidate = shutil.which(name, path=str(fb))
            if candidate:
                return candidate
        raise RuntimeError(f"'{name}' not found on PATH -- is it installed and have you logged in?")
    return resolved


def _redact_key(url):
    """Strip an API key out of a URL before it ever reaches a log, an
    exception message, or a results CSV. An API-key provider's URL carries
    its key as a query param (?key=...), and results_prompts/*.csv gets
    committed -- proj1b's repo is public, so a leaked key here is a real,
    public secret leak, not just a log-noise annoyance."""
    return re.sub(r"([?&]key=)[^&\s]+", r"\1REDACTED", url)


def _post_json(url, payload, headers=None, timeout=180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {_redact_key(url)}: {body[:500]}") from None


def call_ollama(cfg, prompt, file_access=False, session=None, web_access=False):
    """Local model served by Ollama (https://ollama.com). No API key needed.

    No tools of any kind, so web_access is accepted and ignored -- the row
    is logged as web="unavailable" rather than failing. That asymmetry is
    the point of running a local model at all: what it says about the
    market is recall, and comparing it against a model that could look
    things up is real D5 material.

    Ollama's API defaults num_ctx to 2048 regardless of what the model
    actually supports, which silently truncates long prompts. Request a much
    larger window explicitly, and disable the output-length cap
    (num_predict -1) so long answers don't get cut off.
    """
    base_url = cfg.get("base_url", "http://localhost:11434")
    payload = {
        "model": cfg["model"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": cfg.get("num_ctx", 16384),
            "num_predict": cfg.get("num_predict", -1),
        },
    }
    result = _post_json(f"{base_url}/api/generate", payload, timeout=cfg.get("timeout", 300))
    return result.get("response", "")


def call_openai(cfg, prompt, file_access=False, session=None, web_access=False):
    api_key = os.environ[cfg["api_key_env"]]
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": cfg.get("temperature", 0.2),
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    result = _post_json("https://api.openai.com/v1/chat/completions", payload, headers)
    return result["choices"][0]["message"]["content"]


def call_anthropic(cfg, prompt, file_access=False, session=None, web_access=False):
    api_key = os.environ[cfg["api_key_env"]]
    payload = {
        "model": cfg["model"],
        "max_tokens": cfg.get("max_tokens", 1500),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    result = _post_json("https://api.anthropic.com/v1/messages", payload, headers)
    return "".join(block.get("text", "") for block in result.get("content", []))


def call_google(cfg, prompt, file_access=False, session=None, web_access=False):
    """Gemini via API key. Set "grounding": true in config.json to enable
    Google Search grounding -- this is the recommended way to get a
    WEB-CAPABLE Gemini into the run, because the agy CLI's plan mode
    blocks all tool use (see web_capability). Grounded answers come back
    with their own citations in groundingMetadata, which we don't parse --
    the text part carries the URLs the prompt asked for.
    """
    api_key = os.environ[cfg["api_key_env"]]
    model = cfg["model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if web_access and cfg.get("grounding"):
        payload["tools"] = [{"google_search": {}}]
    result = _post_json(url, payload, timeout=cfg.get("timeout", 300))
    parts = result["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def call_cli(cfg, prompt, file_access=False, session=None, web_access=False):
    """Use a subscription (ChatGPT Plus/Pro, Claude Pro/Max, Gemini via
    Antigravity) through its OFFICIAL CLI, already logged in on this
    machine -- not an API key. Each tool has a different non-interactive
    invocation shape, so cfg["cli"] picks which one:

        cfg["cli"] == "claude": `claude -p [--model M]` with the prompt on STDIN (Claude Pro/Max)
        cfg["cli"] == "agy":    `agy -p [--model M] "<prompt>"`    (Gemini, via Google Antigravity)
        cfg["cli"] == "codex":  `codex exec [-m M] -o <tmpfile> "<prompt>"` (ChatGPT Plus/Pro)
                                 codex's stdout is full of session banner
                                 text, so -o writes just the clean final
                                 response to a temp file we then read.

    THE PROMPT MUST GO ON STDIN, NOT IN ARGV, ON WINDOWS. These CLIs are
    npm-installed, so on Windows the thing on PATH is a `.CMD` batch
    wrapper and every call is routed through cmd.exe, which (a) hard-caps
    the whole command line at 8191 characters and (b) does not carry
    newlines inside an argument. Our prompts are multi-line pasted
    evidence, so passing one in argv fails BOTH ways, and only one of them
    is loud:
        > 8191 chars  -> exit 1, "The command line is too long."  (visible)
        <= 8191 chars -> exit 0, but the CLI only ever receives the FIRST
                         LINE of the prompt and cheerfully answers that.
                         Verified in proj1a: a prompt whose last line was
                         "ZEBRA", asked to echo its own last word, answered
                         "else" (the last word of line 1) via argv and
                         "ZEBRA" via stdin. Those rows look like real
                         results and are not -- the more dangerous half.

    Also pass encoding="utf-8" explicitly on every subprocess call. With a
    bare text=True, Python decodes the CLI's UTF-8 output using the Windows
    locale codec (cp1252), which mangles the em-dashes and curly quotes
    these models emit constantly -- or dies outright with UnicodeDecodeError
    ("charmap codec can't decode byte 0x9d"), which run_prompts.py then logs
    as a failed row with an empty response.

    TOOL POSTURE. All three are AGENTIC coding tools that can read/write
    files and run shell commands by default. proj1a banned every tool
    because its prompts were self-contained and explicitly told the model
    to use no outside knowledge. proj1b needs the opposite for the market
    work, so the ban is now selective rather than total:

        BANNED ALWAYS: Bash, Edit, Write, NotebookEdit. Nothing in this
            harness may modify a file or run a shell command -- and Bash
            in particular is a web-access bypass (curl), so it stays out
            even when web_access is on.
        web_access:  WebSearch + WebFetch. ON by default for proj1b.
            claude -> --allowedTools, works.
            codex  -> `--search`. VERIFY with `codex exec --help` on your
                      machine; set "codex_search": false if absent.
            agy    -> not possible in --mode plan, which is also the only
                      thing stopping it writing files. Logged as
                      "unavailable"; use provider "google" with
                      "grounding": true for a web-capable Gemini.
        file_access: Read + Glob + Grep. OFF by default -- unused in
            proj1b, there is no codebase yet.
    """
    cli = cfg["cli"]
    timeout = cfg.get("timeout", 300)
    model = cfg.get("model")

    if cli == "claude":
        # Build the two tool lists explicitly rather than toggling one
        # string, so it is obvious at a glance what is on and what is off.
        allowed = []
        disallowed = ["Bash", "Edit", "Write", "NotebookEdit"]

        if file_access:
            # READ-ONLY. Pre-approved via --allowedTools so headless -p
            # never blocks on a permission prompt.
            #
            # cwd matters as much as the tool list -- Claude scopes file
            # access to its working directory. In proj1b that cwd defaults
            # to this proj_1b folder, which contains our own prompt files,
            # so if you turn this on, point "project_dir" at whatever you
            # actually want it to read instead.
            allowed += ["Read", "Glob", "Grep"]
        else:
            disallowed += ["Read", "Glob", "Grep"]

        if web_access:
            allowed += ["WebSearch", "WebFetch"]
        else:
            disallowed += ["WebFetch", "WebSearch"]

        cmd = [_resolve_cli("claude"), "-p"]
        if allowed:
            cmd.append("--allowedTools=" + ",".join(allowed))
        cmd.append("--disallowedTools=" + ",".join(disallowed))
        if model:
            cmd += ["--model", model]

        # Conversation chaining, always on for this harness. The first call
        # names the session with --session-id, every later one reattaches with
        # --resume, so prompt N sees prompts 1..N-1 and their answers.
        if session is not None:
            if session.get("started"):
                cmd += ["--resume", session["id"]]
            else:
                cmd += ["--session-id", session["id"]]
                session["started"] = True

        cwd = None
        if file_access or session is not None:
            # Claude namespaces stored sessions by working directory, so every
            # call in one conversation MUST share a cwd or --resume cannot find
            # the session.
            cwd = str(cfg.get("project_dir") or CLI_CWD)
            if not Path(cwd).is_dir():
                raise RuntimeError(f"cwd {cwd} does not exist. Fix \"project_dir\" in config.json.")

        # A grounded market survey means real network round trips, so the
        # proj1a default of 300s is tight. Bumped for web runs only.
        eff_timeout = cfg.get("timeout", 600 if web_access else 300)

        # prompt on stdin, never argv -- see the docstring above
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=eff_timeout, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed (exit {result.returncode}): {result.stderr[:500]}")
        return result.stdout.strip()

    if cli == "agy":
        # --mode plan blocks tool use outright, so web_access cannot be
        # honoured here. web_capability() already reports this as
        # "unavailable", so the row is logged honestly instead of failing
        # the whole run -- don't silently drop plan mode to get web, it
        # also re-enables file writes.
        cmd = [_resolve_cli("agy"), "--mode", "plan", "--dangerously-skip-permissions"]
        if model:
            cmd += ["--model", model]
        cmd.extend(["-p", prompt])
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(f"agy CLI failed (exit {result.returncode}): {result.stderr[:500]}")
        return result.stdout.strip()

    if cli == "codex":
        # session is accepted but NOT chained: `codex exec` does have a real
        # resume subcommand (`codex exec resume <id>`), but wiring that up is
        # out of scope here, so every codex call runs as an independent,
        # unchained prompt -- unlike cli='claude'.
        if file_access:
            raise RuntimeError("file_access is only wired up for cli='claude' so far; "
                               "the codex equivalent has not been verified. Leave this row N/A.")
        fd, tmp_path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            # -s read-only blocks writes; reads are still possible here
            # (unlike the other two CLIs), which proj1a noted and accepted.
            cmd = [_resolve_cli("codex"), "exec", "-s", "read-only"]
            if web_access and cfg.get("codex_search", True):
                # `--search` only exists on the interactive `codex` command,
                # not `codex exec` -- the config-override spelling is the
                # one that actually enables the web_search tool here.
                cmd += ["-c", "tools.web_search=true"]
            if model:
                cmd += ["-m", model]
            cmd += ["-o", tmp_path]
            eff_timeout = cfg.get("timeout", 600 if web_access else 300)
            # prompt on stdin, never argv -- see the claude branch above.
            # `codex exec` reads stdin when no PROMPT argument is given.
            result = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=eff_timeout)
            if result.returncode != 0:
                raise RuntimeError(f"codex CLI failed (exit {result.returncode}): {result.stderr[:500]}. "
                                   f"If this mentions the web_search tool, set "
                                   f"\"codex_search\": false in config.json.")
            return Path(tmp_path).read_text(encoding="utf-8").strip()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    raise ValueError(f"Unknown cli '{cli}'. Options: claude, agy, codex")


PROVIDERS = {
    "ollama": call_ollama,
    "openai": call_openai,
    "anthropic": call_anthropic,
    "google": call_google,
    "cli": call_cli,
}


def call_model(cfg, prompt, file_access=False, session=None, web_access=False):
    """file_access=True is for prompts that are SUPPOSED to explore files
    themselves instead of answering from evidence pasted into the prompt
    text. Only the `cli` provider can honour it -- an API-key model has no
    tools and no machine to run them on, so for those we raise instead of
    quietly returning an answer that looks like a file-access result but
    was written blind.

    web_access is deliberately NOT symmetric with that. A model that cannot
    search still has a useful (and gradeable) answer to "name the ten
    closest rivals" -- it is just recall rather than evidence. So instead of
    raising, we run it and let run_prompts.py log web="unavailable" on the
    row. Raising here would knock the local model out of the run entirely
    for exactly the prompts proj1b requires on every model.
    """
    provider = cfg["provider"]
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Options: {list(PROVIDERS)}")
    if session is not None and provider != "cli":
        raise RuntimeError(
            f"conversation chaining is only wired up for provider 'cli' so far; '{provider}' would need its "
            f"own transcript-threading and has not been verified. Set \"chain\": false in config.json."
        )
    if file_access and provider != "cli":
        raise RuntimeError(
            f"This prompt needs file access, which provider '{provider}' cannot do "
            f"(an API-key model has no file tools). Only provider 'cli' can run it. "
            f"Leave this row's verdict as 'N/A - provider cannot read files'."
        )
    return PROVIDERS[provider](cfg, prompt, file_access, session, web_access)
