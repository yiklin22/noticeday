# noticeday

Finds the last day to cancel an auto-renewing contract, shows the clause each
date came from, and puts only the deadlines a person has confirmed on a
calendar.

**The business problem.** Small businesses sign service contracts (waste
collection, equipment leases, software, cleaning, security monitoring) that
renew by themselves unless someone sends notice 30 to 180 days before the
term ends. Nobody tracks the notice date, the window closes, and the business
is locked in for another year. The contract says when. The hard part is
reading it correctly and having the date in front of someone in time.

**What it does.**

1. Upload a contract (PDF with a text layer, or text).
2. It reads the start date, initial term or end date, renewal length, whether
   renewal is automatic, and the notice period. Each value is shown next to
   the highlighted words it came from.
3. A person checks each value, edits it if needed, and confirms with their
   name. Editing after confirming clears the confirmation.
4. The dashboard rolls auto-renewing terms forward to the next notice
   deadline that is still open, and sorts contracts by it. It stops at the
   number of renewals the contract allows ("one (1) additional twelve month
   period").
5. `calendar.ics` holds only confirmed deadlines, each with a reminder
   14 days before.
6. For a confirmed auto-renewing contract, it drafts a non-renewal notice
   letter with the notice clause underneath. It never sends anything.
7. Where renewal is at one party's option, the date by which that party
   must give notice to renew ("Exercise renewal option by").
8. Optional **second reader**: with `NOTICEDAY_MODEL` set, a local model
   reads each upload in the background, about a minute per contract. Each
   value is marked "agrees" or shows the model's different value with its
   quote. Values the model could not back with a quote are listed as such.

![Contract review page](docs/screenshot.png)

Second reader on the same page (before the renewal-limit and duration-comparison fixes it led to):

![Second reader](docs/second-reader.png)

## Ask Claude about your deadlines (MCP server)

`noticeday/mcp_server.py` exposes the contract database to Claude Desktop or
Claude Code over MCP. Three read-only tools:

- `list_deadlines(within_days, confirmed_only)`: what is due, soonest first.
- `get_contract(contract_id)`: the schedule, each value, and the contract words
  it was read from.
- `search_contracts(query)`: find a contract by name or wording.

There are no write tools on purpose. An assistant cannot confirm or edit a
value; every answer says whether a person has confirmed it, and the server's
instructions tell the assistant to say so. Confirming stays in the web app.

```bash
uv pip install -e '.[mcp]'
claude mcp add noticeday -e NOTICEDAY_DB=$PWD/demo.db -- $PWD/.venv/bin/python -m noticeday.mcp_server
```

Then ask "which contracts need notice in the next six months?". Tested with
the MCP Python SDK client in-process (`tests/test_mcp.py`) and over stdio on
the demo database.

## How well it reads contracts: measured on CUAD

[CUAD](https://github.com/TheAtticusProject/cuad) is 510 real commercial
contracts from SEC filings, annotated by lawyers (CC BY 4.0). Its
`master_clauses.csv` ([Zenodo](https://zenodo.org/records/4595826)) gives
normalized answers: effective date, expiration date, renewal term and notice
period. That makes the end-to-end "send notice by" date checkable:
expiration minus notice period, by CUAD's own convention.

Rules were developed on the 407-contract dev split. The model prompt and the
evidence gate were checked on 30 dev contracts. Everything was committed
(`bedc0d0`) before CUAD's 102-contract test split was run once.

### Test split results (102 contracts, run once)

Accuracy is over contracts where the lawyers recorded a value; counts in
brackets. **Wrong** means a value was given and it was wrong (the dangerous
case). **False alarm** means a value where CUAD has none.

| method | expiration | renewal length | notice period | send-notice-by date |
|---|---|---|---|---|
| rules | 44.1% (26/59), 9 wrong, 4 false alarms | 73.9% (17/23), 0 wrong, 3 FA | 84.6% (11/13), 0 wrong, 2 FA | 2/10, 2 wrong |
| model, no gate | 61.0% (36/59), 7 wrong, 11 FA | 91.3% (21/23), 0 wrong, 2 FA | 84.6% (11/13), 0 wrong, 12 FA | 4/10, 3 wrong |
| model, gated | 44.1% (26/59), 5 wrong, 9 FA | 82.6% (19/23), 0 wrong, 2 FA | 84.6% (11/13), 0 wrong, 9 FA | 1/10, 3 wrong |
| union (rules, else gated model) | **62.7% (37/59)**, 8 wrong, 10 FA | 87.0% (20/23), 0 wrong, 5 FA | **92.3% (12/13)**, 0 wrong, 9 FA | 4/10, 3 wrong |
| agree (both give the same value) | 27.1% (16/59), 2 wrong, 3 FA | 69.6% (16/23), 0 wrong, 0 FA | 76.9% (10/13), 0 wrong, 2 FA | 0/10, 1 wrong |

Full tables: `docs/results/test-*.md`. What the numbers say:

- **Renewal and notice periods are found well; the expiration date is the
  weak link.** Even the best method gets the initial end date right in only
  63% of contracts, and "send notice by" needs both. Only 10 test contracts
  have both an expiration date and a notice period, so the end-to-end column
  is too small to rank methods. Treat it as a smoke test, not a result.
- **Wrong deadlines come from the start date**, not the arithmetic: in all
  three wrong union deadlines the start date was a few days or years off
  (the signing date or a recital date instead of the effective date).
- **The evidence gate cut wrong expiration dates from 7 to 5 but also
  dropped 10 correct ones.** Most dropped ones were correct values the model
  computed (a term from an end date), which the gate refuses by design.
  For renewal and notice it cost 2 correct renewals and removed 3 notice
  false alarms. It is a precision tool, and it costs recall.
- **When rules and model agree, they are rarely wrong**: 2 wrong
  expirations out of 21 agreed values, and no wrong renewal or notice
  values. But they agree on few contracts. That fits a review queue:
  agreement marks a value as lower risk, and everything else goes to a
  person. It does not justify skipping the person.
- **Most of the model's notice "false alarms" are real deadlines CUAD does
  not count**: notice to *exercise an option to extend* ("must notify
  Airspan at least six (6) months prior to the end of the Initial Term"),
  or to negotiate an extension. A business would want those on the calendar
  too, so the app should treat them as a second kind of deadline rather
  than discard them. Some are true errors (termination-for-convenience
  notice).
- Speed: the 4B model took 46 s per contract on 8 CPU threads (79 minutes
  for 102 contracts); the rules take about 10 ms.

### After the test run: term-rule fixes (13 Nov 2026)

The table above is the one run on the frozen code. Afterwards, working on
the dev split only, I fixed why the rules missed 104 dev expiration dates:

- **The survival filter was too broad.** Any "after", "following" or
  "thereafter" next to a duration counted as a survival clause, so "three (3)
  years after the Effective Date" and "ten (10) years thereafter" were thrown
  away. Now it only counts when the words refer to termination or expiry, or
  follow "during the term".
- **Terms that count from an event** ("ten (10) years after the First
  Commercial Sale") are left for a person, because they have no fixed end
  date.
- **More ways to state the end:** "take effect", "come into force",
  "up to and including", "until the earlier of (i)", "TERM: <date> to <date>".

| split | method | expiration before | expiration after | deadline before | deadline after |
|---|---|---|---|---|---|
| dev | rules | 45.7% (113/247), 30 wrong, 22 FA | 53.4% (132/247), 28 wrong, 21 FA | 24 right, 8 wrong | 28 right, 8 wrong |
| test | rules | 44.1% (26/59), 9 wrong, 4 FA | 45.8% (27/59), 7 wrong, 4 FA | 2/10, 2 wrong | 3/10, 2 wrong |
| test | union | 62.7% (37/59), 8 wrong, 10 FA | 64.4% (38/59), 7 wrong, 10 FA | 4/10, 3 wrong | 4/10, 3 wrong |

**Renewal wording (same day).** A second pass on dev added renewal phrasings
the rules missed: "renewing annually", "renewed tacitly every year",
"extend automatically for monthly periods", "half a year", Roman numerals
("one (I) year"), and "successive terms of the same duration" (the renewal
equals the initial term). Dev renewal went from 74.2% (92/124, 4 wrong) to
83.9% (104/124, 3 wrong); dev notice from 57 to 59 correct. On test it
changed nothing that counts: renewal stays 17/23 (one fewer false alarm).
Two dev deadlines moved from "needs facts" to wrong: the renewal is now
found, and the start date was a few days off, which is the known weak point.

The test split was run several times to get the "after" figures (once per
change, no test-driven edits), so it is no longer untouched. The gain on test (+1 correct, -2 wrong) is much smaller
than on dev (+19 correct, -3 wrong): most of the dev gain came from wording
that is common in the dev contracts, and it does not carry over to new
contracts as strongly. Renewal and notice figures did not change.

## Extraction methods

- **rules** (`noticeday/extract.py`): regular expressions for dates,
  durations and number words, plus sentence scoring. They skip cure periods
  ("within 30 days after notice of breach"), survival clauses ("for five
  years after termination") and extensions that need both parties to agree.
- **model** (`noticeday/model.py`): Qwen3-4B-Instruct-2507 on CPU (about 47 s
  per contract, 8 threads, no GPU, no API). It reads the preamble plus the
  highest-scoring term sentences and answers in JSON, with a verbatim quote
  for each value. **Evidence gate:** a value is kept only if its quote is in
  the contract *and* the value can be parsed back out of the quote. On dev
  the gate dropped values the model had computed or restated: a term derived
  from an end date, "two (2) months" restated as 60 days, "perpetual" backed
  by an unrelated sentence. A dropped value is shown as "not found", so a
  person fills it in.
- **union**: the rule value if there is one, otherwise the gated model value.
- **agree**: a value only where rules and the gated model give the same one.

The app always runs the rules (instant). The model runs as the optional
second reader in the app, or in batch with `scripts/run_model.py`.

**What the second reader caught on its first live run.** On a dev contract
both readers agreed on everything except how to write the renewal ("12
months" vs "1 year"; durations are now compared as durations). Its quote,
"automatically renewed for **one (1) additional** twelve month period",
showed a gap in the scheduler: it rolled the contract forward nine times to
a 2027 deadline, but the contract allows one renewal and ended in 2019.
Renewal limits are now extracted and respected. On the dev split the rules
find 8 limits, all correct on inspection, but only 2 of the 6 renewal
answers where the lawyers wrote a count. A missed limit is the most
dangerous error left: it shows a deadline for a contract that has already
ended. It is a reason the review step stays.

## Run it

```bash
uv venv && uv pip install -e . pytest httpx
pytest -q                                   # 33 tests (4 need '.[mcp]')
python scripts/seed_demo.py demo.db         # needs data/cuad (below); or upload your own
NOTICEDAY_DB=demo.db uvicorn noticeday.app:app --port 8830
# second reader: add NOTICEDAY_MODEL=<Qwen3-4B-Instruct-2507 folder> and pip install -e '.[model]'; needs ~8 GB RAM
```

Reproduce the measurements (downloads about 125 MB of CUAD data):

```bash
mkdir -p data/raw && cd data/raw
curl -L -o cuad.zip https://github.com/TheAtticusProject/cuad/raw/main/data.zip && unzip cuad.zip -d cuad
curl -L -o full.zip "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1" && unzip full.zip 'CUAD_v1/master_clauses.csv'
cd ../.. && python scripts/prepare_cuad.py
python scripts/evaluate.py --split test --method rules
uv pip install -e '.[model]'                # torch + transformers, CPU is enough
NOTICEDAY_MODEL=<folder with Qwen3-4B-Instruct-2507 weights> python scripts/run_model.py --split test
for m in model_raw model union agree; do python scripts/evaluate.py --split test --method $m; done
```

## What this does not show

- **No real customer.** CUAD contracts are large-company SEC exhibits
  (licences, supply, distribution), not a café's waste-collection or
  photocopier lease. Small-business contracts are shorter and more often
  pre-printed forms. Whether accuracy holds on those is unmeasured.
- **The test split is 102 contracts**, and only a minority have a renewal
  or notice period at all. The per-field counts are small and the intervals
  wide; the tables give raw counts so they can be read that way.
- **Date convention.** CUAD (and this tool) take "two years from 14 Feb
  2019" to end on 14 Feb 2021, and notice "60 days before" to be due 60 days
  earlier. Some contracts define it differently ("the day before the
  anniversary", business days). The review page shows the clause so a
  person can check it.
- **Scanned PDFs** without a text layer are rejected; there is no OCR step.
- **No login, no multi-user accounts, no email reminders.** The calendar
  file is the reminder channel. These would come before any real pilot.
- Amendments that change the term are not linked to the original contract.
- **Option deadlines are rules-only and unmeasured.** "Notify us six months
  before the end of the term if you want to extend" is a deadline too. Since
  milestone 8, the rules extract it when renewal is not automatic, and the
  dashboard shows "Exercise renewal option by". CUAD has no label for it. By
  my own reading of the 9 dev-split hits: 6 right, 2 borderline (a
  franchisor's notice; a renewal the parties must both agree to), 1 wrong.
  That is an inspection, not a measurement.
- Evergreen month-to-month continuations ("thereafter continues on a month
  to month basis until terminated") are often missed by the rules.
