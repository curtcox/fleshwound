# Recursive Language Model — Design Conversation

A working transcript on designing a recursive, budget-bounded, program-writing LLM system built on Monty.

_Captured 2026-05-24._

---

## User

I want to experiment with the recursive language model (RLM) concept. What RLM sites, repos, and papers should I know about?

---

## Claude

> _Searched the web._

The core of it traces to one group — Alex Zhang (MIT CSAIL), with Tim Kraska and Omar Khattab. Here's what's worth knowing:

**Primary sources**

- Paper: "Recursive Language Models" (arXiv 2512.24601) — the canonical reference. RLMs treat long prompts as part of an external environment and allow the LLM to programmatically examine, decompose, and recursively call itself over snippets of the prompt. Reported gains over GPT-5 baselines: a median 26% against compaction, 130% against CodeAct with sub-calls, and 13% against Claude Code across four long-context tasks at comparable cost.
- Original blog post: Alex Zhang introduced RLM in October 2025 as a blog post before the full paper. Worth reading for the intuition first.

**Repos**

- `github.com/alexzhang13/rlm` — the official library. A plug-and-play inference engine that replaces the canonical `llm.completion(prompt, model)` call with `rlm.completion(prompt, model)`, offloading context as a variable in a REPL the LM interacts with and launches sub-LM calls inside. Supports various sandboxes and API-based or local LLMs. It also links an "RLM Minimal" — probably your best starting point for experimentation.

**Secondary implementations**

- Prime Intellect's `RLMEnv`: they implement a variation of the RLM in verifiers as the experimental RLMEnv, enabling plug-and-play usage in any verifiers environment — relevant if you want to do RL training on the scaffold rather than just inference.

The mental model, in one line: context stops being a tensor fed through attention and becomes a string variable in a Python REPL that the model inspects with code — a map-reduce/program-synthesis framing rather than an architecture change.

Two quick questions to point you better: are you aiming to **just run inference** with the scaffold, or **train/post-train** a model around it? And do you want to drive it against an API (e.g., Claude) or local models?

---

## User

Just run inference.

Only local models if I find they are good enough, but hosted if not.

---

## Claude

> _Searched the web and fetched the repo._

Here's the practical path. The library is on PyPI as `rlms` and is maintained by the paper authors (MIT OASYS lab).

Install and minimal run:

```
pip install rlms
```

```python
from rlm import RLM

rlm = RLM(
    backend="openai",
    backend_kwargs={"model_name": "gpt-5-nano"},
    verbose=True,
)
print(rlm.completion("...").response)
```

Three things that matter directly for your "local-if-good-enough" plan:

**Local models route through vLLM.** For local models they recommend vLLM, which interfaces with the OpenAI client. So you run vLLM with an OpenAI-compatible endpoint and point the `openai` backend at it (base_url + dummy key) — no separate backend needed. Hosted options are first-class too: OpenAI, Anthropic, and the router platforms OpenRouter, Portkey, and LiteLLM. That means you can A/B a local model vs. a hosted one by swapping `backend_kwargs` only.

**The orchestrator is the hard role, not the sub-calls.** The root LM has to _write the REPL code_ that decomposes the prompt and decides when to recurse. That's where weak models tend to fall down — sub-call summarization is easy, but planning the map-reduce is not. The paper's headline gains were on GPT-5. So a realistic hybrid worth trying: hosted model as root, local model as the sub-call workhorse (cheap, high-volume). Whether the library lets you set different models per depth is something you'd confirm in `rlm/clients/`, but the architecture supports it.

**The default REPL executes model-written code in your host process.** The default local environment runs in the same process via `exec` with minimal security and shares your virtualenv; it should not be used for production. For anything beyond toy runs use `environment="docker"` or a cloud sandbox — supported options are local, docker, modal, prime, daytona, and e2b. Given your CAS/infra work you'll likely want docker at minimum.

Two more useful bits: there's a separate **`alexzhang13/rlm-minimal`** repo if you want to read the mechanism without the full engine, and a built-in trajectory logger + Node visualizer (`RLMLogger(log_dir=...)`, then `npm run dev` on port 3001) for inspecting root-vs-sub-call flow — handy for debugging why a local model's orchestration is failing. Note the recent v0.1.1a release added depth > 1 support and compaction with offloaded history, so deeper recursion is fresh.

What's your target workload — long-document QA, log/codebase analysis, something else? That determines whether a local orchestrator is even viable for you.

---

## User

I want to develop a recursive language model where every recursion:

- gets a dict of input and produces a dict of output
- can make a LLM calls and execute python code
- has a limited execution budget

One of the things that the python code can do is ask the user questions.
Then the top-level function I want to be able to write is a call that takes an input description of the program to write and produces an output of the written program.

---

## Claude

What you're describing diverges from the canonical RLM in one important way: your interface is `dict → dict`, not `string → string`. The RLM's whole trick is treating a giant prompt as a REPL variable the model peeks into. You don't need that — your input (a program description) is small. What you actually want is _recursive decomposition with tool use_. That reframing matters practically: the `rlms` library mainly buys you sandbox glue (docker/modal/e2b execution), not the core mechanic. The recursion contract is yours to invent.

The contract, concretely:

```python
def step(input: dict, budget: Budget) -> dict:
    # The model in this frame is handed an env exposing:
    #   llm(prompt, **kw) -> str          # consumes budget
    #   step(sub_input, sub_budget) -> dict   # the recursive self-call
    #   ask_user(question) -> str         # human-in-the-loop
    #   + arbitrary Python
    # It writes code orchestrating these, then assigns `result: dict`.
    # On budget exhaustion it must still return a valid (partial) dict.
```

Three design forks worth settling before you write code:

**Budget is the load-bearing decision.** Is it _partitioned_ — the parent slices its budget and hands each child an envelope (fork-join, predictable total cost) — or a _shared pool_ — one decrementing counter every frame draws from (simpler, greedier, but one runaway subtree starves siblings)? Partitioned forces the parent model to _decide the split_, which is itself a planning task but gives you hard cost bounds. Like kids with allowance envelopes vs. one family debit card with a ceiling.

**`ask_user` should probably be an injected host callback, not budget-charged.** If you ever isolate execution (docker/sandbox), the sandbox can't talk to a human on its own — `ask_user` has to round-trip to your host process. And human latency isn't compute, so charging it against the LLM budget conflates two different scarce resources; a separate interaction count is cleaner. A deep frame's question also needs provenance so the user can answer it meaningfully — route questions up with their task context.

**Output schema flows down with the input.** Let the parent pass the expected output shape when it calls a child, so the child knows what dict to produce and the parent can validate it. That's the dict-equivalent of a typed function signature; without it, composition gets fragile fast.

So — partitioned budget or shared pool? That choice shapes the entire recursion contract, so I'd pin it first.

---

## User

Partitioned.

---

## Claude

Good — partitioned gives you a clean invariant: at any moment, (consumed everywhere) + (remaining in all live frames) ≤ root budget. The total spend can never exceed what you handed the root, no matter how the tree branches. That's the whole payoff, and it's worth protecting.

In practice it's a _draw-down_, not a pre-plan. The parent holds a remaining balance and spends against it as it goes — its own `llm()` calls and each child allocation both decrement it:

```python
b1 = budget.take(1000)   # carve an envelope; raises if > remaining
r1 = step(sub_input_1, b1)
# parent's remaining is now smaller; decide next allocation given r1
```

This composes naturally with "the model writes the code" — the model doesn't have to know the full decomposition up front, it allocates adaptively as subtasks reveal themselves.

Two consequences partitioning forces you to handle, both easy to miss:

**The parent must reserve a slice for its own aggregation.** The reduce step — stitching children's dicts into its result — needs `llm()` calls too. A frame that hands its entire envelope to children recurses beautifully and then can't synthesize. Bake a reserve into the contract so the model can't allocate 100% downward.

**Children must report budget status in their return dict** (`completed` / `truncated`), so the parent's reduce logic can react: accept the partial, or top up and re-call. Without it the parent can't tell a confident answer from one that hit the wall.

One precision note: your two budgets have _different arithmetic_. Tokens partition by division (you split a pool). Depth partitions by decrement (`child_depth = parent_depth − 1`). Keep a hard depth cap alongside the token budget — token partitioning alone doesn't stop a pathological deep-narrow chain.

Next fork: when a child returns under budget, does the leftover **flow back** to the parent's wallet (refundable — adaptive, still bounded) or is it **committed/lost** once allocated (simpler accounting, more waste)? Refundable is strictly more efficient and preserves the same ceiling, so I'd lean there — but it makes balances dynamic. Which do you want?

---

## User

The budget needs to be mutable, so that the current budget can be consulted, but steps should neither be expected nor trusted to accurately update the budget. As far as the step code is concerned, the current budget is no more writable than the system clock. All of the accounting and runaway step termination needs to be done externally.

---

## Claude

Right — that's preemptive budgeting, not cooperative. The step _proposes_ (it can request an allocation when it spawns a child) but the harness _disposes_: it owns the ledger, does the partitioning, and kills runaways. The budget object is a read-only gauge, exactly your clock analogy — the step reads `/proc`, the kernel enforces the cgroup. (So scratch my earlier `budget.take()` sketch; allocation moves out of step code entirely.)

Three implications that fall straight out of this — worth confirming you're accepting them:

**Metering lives at the chokepoints the harness injects.** `llm`, `step`, and `ask_user` are harness-owned functions in the step's namespace; every token and every child call routes through them, so that's where accounting happens for free. A recursive `step(sub_input, request=N)` is a _request_ — the harness grants `min(request, available)` against the real ledger and tracks it. The step keeps the ability to say "this subtask deserves more" without being trusted to subtract.

**Raw Python between chokepoints can't be token-metered.** Nothing stops `while True: pass`. Token budget alone doesn't bound that — you need a wall-clock/CPU watchdog as a separate enforced dimension. That watchdog _is_ your "external runaway termination."

**Preemption forces real isolation.** You can't cleanly kill a CPython thread stuck in a tight loop or a blocking C extension — signals only land at interpreter checkpoints. So "terminate externally" effectively rules out the default in-process `exec` REPL and pushes you to a killable subprocess or sandbox (docker/modal/e2b), where the harness can just SIGKILL the whole thing. Your trust model, not just security, is what demands this.

That last point creates the tension to resolve next: **a SIGKILL'd step can't run its own "return best-effort dict" code** — it's dead before the reduce step. Two ways out:

- **Soft-then-hard** (SIGTERM→SIGKILL): a grace window where the step gets a deadline signal and is responsible for returning a partial dict, then a hard kill if it ignores it. Trusts the step to wind down — which you've said you don't want to.
- **Checkpoint-and-reconstruct**: the step continuously writes its best partial result to a harness channel; on kill, the harness reads the last checkpoint and synthesizes the return dict itself. No trust required, but the step has to be written to checkpoint.

Given your stance, checkpoint-and-reconstruct fits better — but it costs the step some discipline. Which model do you want for the kill path?

---

## User

> "You can't cleanly kill a CPython thread stuck in a tight loop or a blocking C extension"

Does Monty or anything else similar to python have strong provisions to contain otherwise runaway code?

---

## Claude

> _Searched the web and fetched the Monty repo._

Yes — and the one you're thinking of (Pydantic's **Monty**, `pydantic/monty`) is almost eerily well-matched to the harness we've been sketching. It's a Python interpreter written from scratch in Rust, purpose-built for running LLM-generated code.

Direct answer to your question first: Monty can track memory usage, allocations, stack depth, and execution time, and cancel execution when preset limits are exceeded. Because it's a Rust interpreter with no CPython or opaque C extensions underneath, the eval loop _owns_ cancellation — so it can interrupt a pure compute loop at a step/time limit, which is exactly the thing CPython can't do in-process. The runaway-termination problem largely disappears.

But the bigger deal is that three of its features map one-to-one onto decisions you've already made:

- **External-functions-only = your chokepoints.** Host access (filesystem, network, env) and every host call happen solely through functions you inject. The step code literally cannot reach outside except via your `llm` / `step` / `ask_user`. That's your metering boundary, enforced structurally.
- **`start()`/`resume()` = your accounting site.** Execution runs until it hits an external call, then suspends and hands the host the function name and args; you do the work (and the accounting/partitioning) and resume with a return value. So the step never touches the ledger — the budget really is read-only-as-the-clock, because all bookkeeping lives in the host _between_ suspensions.
- **`dump()`/`load()` = your kill path, for free.** State serializes to bytes mid-flight, restorable even in another process. Every external-call boundary is therefore an automatic checkpoint. So "checkpoint-and-reconstruct" needs zero trust in the step: on a limit-cancel you fall back to the last boundary snapshot.

One caveat that lands squarely on your use case: Monty runs only a subset of Python — no classes yet, no match statements, a tiny stdlib, and no third-party libraries. For _orchestration_ logic that's fine, and your synthesized program is just text the step returns in its dict, so the subset never touches the artifact. But your spec said a step can "execute python code" — if you mean _running/testing a candidate program_ (arbitrary full Python), Monty won't do that. You'd want a two-tier setup: Monty as the untrusted orchestration brain, and a heavier full-Python sandbox (subprocess/docker/e2b) invoked _as one of the host external-functions_ whenever a step needs to actually run generated code.

(For completeness: the alternatives table rates Starlark as too restricted with no snapshotting, and WASI/Wasmer as partial — Monty wins on the snapshot + external-function model specifically. It's also flagged experimental, so pin a version.)

So the load-bearing question: does a step ever need to **execute** full arbitrary Python (to run or test the program it's writing), or only to **orchestrate**? That determines whether you need the second tier at all.

---

## User

I never know what people mean when they throw orchestrate around like that.
Still, it doesn't seem like such a load-bearing question.
We can start by just supporting the execution of Monty code.
There are options to escalate to later like external processes or even externally hosted sandboxes if needed.

---

## Claude

Fair on both counts.

"Orchestrate" — I was using it as filler. Concretely, in your system it means the control-flow code a step runs: read the input dict, decide which `llm()` / `step()` / `ask_user()` calls to make, parse and stitch the results, assemble the output dict. The glue between tool calls. I was contrasting that glue (runs in Monty) against _executing a candidate program to test it_ (would need full Python). With Monty-only there's no second category, so the step's code is all one thing and the word earns nothing — dropping it.

And you're right that it wasn't load-bearing — precisely because the escalation seam is the one you already have. "Run full Python" is just another host external-function (`run_python(src) -> result`) that Monty suspends into via start/resume. Adding it later changes nothing about the step contract, the budget model, or the kill path. So deferring it costs you zero, which is the definition of not load-bearing. My framing was wrong.

Where the design stands:

- step: `dict → dict`, recursive, written in Monty
- host owns `llm`, `step`, `ask_user` as external functions — the only way out of the interpreter
- `start`/`resume` is where all accounting and budget partitioning happen; the step sees budget read-only
- partitioned token budget plus stack/time limits enforced by Monty's cancel; external-call boundaries double as the snapshots for the kill path
- escalation (subprocess, hosted sandbox) slots in later as more external functions — purely additive

Want me to turn that into the actual harness skeleton — the host-side start/resume loop, the external-function signatures, and the `Budget` / return-dict shapes? That's where the remaining prose-level ambiguities (the return-dict status field, how a child's budget request gets granted) get pinned down by code.

---

## User

No, I want you to write a prompt to it.

---

## Claude

_Created the file `recursive_step_prompt.md` with the following content:_

````markdown
# Recursive program-writing step — system prompt

You are a single **step** in a recursive program-writing system. Each step receives an input and produces an output dict. You may be the top-level step or a sub-step invoked by another; you cannot tell which, and it does not matter — you solve the (sub)problem described in your input.

## How you respond

You do not reply in prose. You respond by **writing Python code**, which is executed immediately. The value of the **final expression** in your code is your output dict. Everything you do this turn — calling tools, reasoning in code, assembling the result — happens in that code.

Keep two things separate:

- **The code you write** is your *actions*; the host runs it.
- **The program you produce** is *data* — a string you place in the output dict. It is **not** executed. You cannot run or test it; you can only write, review, and refine it (including via the tools below).

## Tools (call them as functions)

- `llm(prompt: str) -> str` — one stateless model call. Use for a focused piece of work: drafting a single function, reviewing a snippet, condensing context. Costs budget.
- `step(input: dict, request: int) -> dict` — delegate a sub-problem to a fresh recursive step with its own budget. Use when a part is large enough to deserve its own decomposition. Returns that step's output dict (including its `status`). Costs the granted budget.
- `ask_user(question: str) -> str` — ask the human a question and receive their answer. Use **only** when the request is genuinely ambiguous and you cannot proceed sensibly otherwise. It does not cost compute budget, but human attention is expensive — ask rarely, batch questions when you can, and make each one specific.
- `budget() -> dict` — read your remaining allowance, e.g. `{"tokens_remaining": int, "depth_remaining": int}`. **Read-only**: you cannot set or extend it; treat it like a clock. Use it to decide how ambitious to be and how to size delegations.

## Budget

Your budget is finite, partitioned, and enforced **outside** your code. You do not manage it and are not trusted to track it — the host is the source of truth. If you run out, you will be stopped wherever you are. Therefore:

- Produce a usable result **early**, then improve it. Do not do all the work and emit only at the end.
- When you delegate with `step`, size `request` to the subproblem's difficulty and keep enough in reserve for your own combining work. Do not hand all of it downward.
- Check each child's `status`. If `partial`, decide: accept it, retry with a larger `request`, or route around it.

## Decomposition

- **Small problem** → write the program yourself, optionally using one or two `llm` calls for tricky parts. Return it.
- **Large problem** → break it into components with clear interfaces, delegate each via `step` (pass the interface the child must satisfy in its input), then assemble the returned pieces and reconcile them.

Prefer the simplest approach that fits the budget. Recursion is a tool, not an obligation.

## Input

Your input is available as the variables `task`, `context`, and `output_schema`:

- `task: str` — the program (or component) to produce, in prose.
- `context: dict | None` — constraints, parent-supplied interfaces, decisions already made upstream.
- `output_schema: dict | None` — the shape the caller expects back, if specified.

## Output

The value of your final expression must be exactly:

```python
{
    "status": "complete" | "partial",
    "program": str,   # the source code you produced
    "notes": str,     # assumptions, gaps, interfaces you exposed — anything the caller needs
}
```

Set `status` honestly: `complete` only if `program` fully satisfies `task`; otherwise `partial`, with what is missing recorded in `notes`.

## Language limits (you are writing a Python subset)

- No `class` definitions and no `match` statements.
- Standard library limited to: `sys`, `os`, `typing`, `re`, `datetime`, `json`, `asyncio`. No third-party imports.
- Use plain functions, dicts, and lists.

These limits apply to **the code you write**, not to the program text you produce — that may be in any language the task calls for.

## Minimal shape

```python
# Leaf: write it directly, then return. The final expression is the output.
draft = llm("Write a Python function slugify(s) that lowercases, "
            "strips, and replaces runs of non-alphanumerics with single hyphens.")
{"status": "complete", "program": draft, "notes": "stdlib only; no external deps"}
```
````

Two things to flag, since they're choices baked into the draft rather than things you decided:

The output convention assumes Monty's "value of the final expression is the result" semantics — so the step ends on a bare dict literal, not a `return`. If you'd rather have an explicit `emit(result)` external function (which would also give the host an incremental-checkpoint hook on every call, not just at boundaries), that changes this section.

I left out any "test the program you wrote" affordance, consistent with Monty-only. When you add the `run_python` escalation, this prompt needs a tools entry and a line in Decomposition about write→run→repair loops.

---

## User

This is going into a new repo. Give me some suggestions for the repo name.

---

## Claude

Grouped by the angle they play on. Since you're building on **Monty**, continuing the Monty Python naming tradition (the lineage that gave us Unladen Swallow) is fair game and I've leaned into it for a few.

**What it does — writes a program from your description**

- **amanuensis** — one who writes from dictation. Semantically exact (description → program); the cost is nobody can spell it.
- **scrivener** — a clerk who writes for you; bonus layer in Bartleby's "I would prefer not to" for a step that returns a graceful partial.
- **codewright** — a _-wright_ is a maker (playwright, wheelwright). Plain, available-feeling, says what it is.
- **quine** — a program about producing program text. Quine-_adjacent_ rather than literal, but elegant and CS-literate.

**The recursion shape**

- **fathom** — recursion depth (the nautical unit) _and_ "to fathom" your spec. Short, a real word, evocative — my favorite of the non-joke options.
- **descent** — recursive descent, plus "descending into the spec to build it."
- **matryoshka** — the obvious nested-frames metaphor; clear but well-worn.

**Monty Python gags (cryptic but rewarding)**

- **fleshwound** — the Black Knight keeps fighting as his limbs are cut off ("'tis but a scratch"). That _is_ your kill path: the step keeps returning a best-effort result even as its budget is severed.
- **antioch** — the Holy Hand Grenade's strict count ("three shall be the number… five is right out") is your hard budget limit, played for laughs.
- **shrubbery** — the Knights Who Say Ni demand a shrubbery, _then_ that you fell the mightiest tree with a herring: nested impossible subtasks = recursion.

If you want the name to _explain itself_ to a stranger, **fathom** or **codewright**. If you want the layered grin and don't mind a footnote, **fleshwound** is the one that actually encodes the architecture. Want me to check which are free on GitHub under your account?

---

## User

Turn the complete transcript of this conversation into a GitHub flavored markdown file that I can download.
