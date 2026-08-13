# [Char3] ASMR Question — Writing Agent

n8n workflow that generates question→payoff script pairs for the Char3 ASMR
weightlifting question-format content lane and writes them into Supabase.

- **Workflow ID:** `NOlaieLLePKs3HiN`
- **Name:** `[Char3] ASMR Question — Writing Agent`
- **n8n project:** `Garreth Dottin <garreth@arborvita.io>` (personal)
- **URL:** https://czed.app.n8n.cloud/workflow/NOlaieLLePKs3HiN

## What it does

On each run it:

1. Reads an input `count` (default `5`).
2. Fetches existing hooks (batch `char3_asmr_q`) from Supabase so it can avoid duplicates.
3. Asks an LLM (OpenRouter, model `google/gemini-2.5-flash`) to write `count` NEW
   question→payoff pairs in the house style.
4. Parses the JSON the model returns into one item per pair.
5. Inserts each pair as a row into Supabase table `char3_asmr_hooks`.

### House style enforced in the prompt

- **Slide 1 (hook):** short, punchy QUESTION, under 12 words, no hashtags/emojis.
- **Slide 2 (payoff):** 1–2 sentences answering the hook. Theme = "a cheat code
  plus hard work" (metabolic health / gym effort / a science-y edge). **Never**
  names a drug, medication, peptide, brand, or compound.
- ~1 in 3 payoffs ends with a single emoji; the rest have none.
- No em dashes, no ampersands (uses commas / "and").
- Must not duplicate or reword any hook already in the table.

## Trigger / inputs

- **Manual Trigger** — primary; click "Execute workflow" in n8n.
- **Weekly Schedule (disabled)** — a disabled stub (Mondays 09:00, weekly). Enable
  it to run on a cadence.
- **Input:** optional `count` (integer). When omitted it defaults to `5`. Pass it
  in the JSON body / pinned data of the trigger, e.g. `{ "count": 10 }`.

## Nodes (in order)

| Node | Type | Purpose |
|------|------|---------|
| Manual Trigger | `manualTrigger` | On-demand run |
| Weekly Schedule (disabled) | `scheduleTrigger` | Disabled cadence stub |
| Set Count | `set` | `count = {{ $json.count || 5 }}` |
| Get Existing Hooks | `httpRequest` (GET) | Supabase `select=hook&batch=eq.char3_asmr_q&limit=500` (alwaysOutputData so an empty table still proceeds) |
| Build Prompt | `set` (executeOnce) | Composes `promptSystem` + `promptUser` (injects count + existing hooks) |
| Generate Pairs (OpenRouter) | `httpRequest` (POST) | `POST https://openrouter.ai/api/v1/chat/completions`, model `google/gemini-2.5-flash`, temp 0.9 |
| Parse Pairs | `code` | Extracts JSON array from the completion, one item per `{hook, payoff}` |
| Insert Row | `httpRequest` (POST) | Inserts each pair into `char3_asmr_hooks` |

## Credentials needed

| Node(s) | Credential type | Bound credential |
|---------|-----------------|------------------|
| Generate Pairs (OpenRouter) | `httpBearerAuth` | `OpenRouter API Key` (`SVSDm02sBIRA2I5k`) |
| Get Existing Hooks, Insert Row | `supabaseApi` (predefined) | `Supabase Service Role` (`BpJOuYVDTTtsYa5o`) |

> **Verify:** the Supabase URL is hard-coded to project
> `qlcmgxgwpzmiebzxflai`. The bound `Supabase Service Role` credential must hold a
> key valid for **that** project. If it points elsewhere, swap it for the correct
> project's `supabaseApi` (service_role) credential on both HTTP nodes.

## Target table schema — `char3_asmr_hooks` (project `qlcmgxgwpzmiebzxflai`)

Columns written per row:

| Column | Value |
|--------|-------|
| `hook` | slide-1 question string |
| `payoff` | slide-2 payoff string |
| `batch` | `char3_asmr_q` |
| `gate_status` | `approved` |
| `used` | `false` |

(Any `id` / `created_at` columns are expected to be DB-defaulted.)

## How to run

1. Open the workflow in n8n (URL above).
2. Confirm the two credentials are attached and the Supabase credential targets
   `qlcmgxgwpzmiebzxflai`.
3. Click **Execute workflow**. To generate a different quantity, pin/pass
   `{ "count": N }` on the Manual Trigger.
4. Check the `Insert Row` node output, then confirm the new rows in the
   `char3_asmr_hooks` table.

## Notes / status

- **Not published/active.** n8n cannot activate a manual-trigger-only workflow.
  The workflow is saved and runs on demand. To run it on a schedule, enable the
  `Weekly Schedule (disabled)` node, then publish/activate.
- The LLM route uses OpenRouter (`google/gemini-2.5-flash`) with the existing
  OpenRouter bearer credential, per the model requirement for this lane.
