# Wilson Pipeline Improvements -- Design Spec
**Date:** 2026-04-03
**Status:** Approved
**Version target:** v0.1.0

---

## Purpose

Three independent pipeline improvements that make Wilson more correct, more
honest, and more useful without changing its core verification logic.

Each improvement addresses a real gap identified during v0.0.5 development
and testing:

1. **Blocked flag compliance** -- Wilson was running Phase 2 and Phase 3 on
   opinions that individuals had requested be de-indexed from search engines.
   This violates CourtListener's stated privacy policy and the spirit of the
   removal system even if it doesn't violate the letter of the API terms.

2. **Name-based lookup confidence threshold** -- Wilson's fallback to name-based
   search was proceeding silently even when the top result was a poor match.
   A user typing "Smith v. Jones" could inadvertently verify the wrong case.

3. **CSV update notification** -- The bulk citation CSV is dated. Users had no
   way to know when newer data was available. Wilson should inform without
   auto-downloading.

---

## Improvement 1: CourtListener `blocked` Flag Compliance

### Background

CourtListener allows individuals to request that their cases be de-indexed
from public search engines. When approved, the cluster object in the API
carries `blocked: true`. CourtListener explicitly asks API users to check
this flag before republishing or further processing case content.

From their API documentation:
> "If you plan to use this data on the Internet, carefully consider how you
> will protect these people and their privacy wishes. The simplest way to do
> that is to use the `blocked` flag that's available on most objects."

Wilson does not republish case content, but Phase 2 fetches full opinion text
and Phase 3 sends it to an LLM. Both of these constitute further processing
of content that the subject has asked to restrict. Respecting the blocked flag
is the right thing to do.

### Design

**Where:** After Phase 1 confirms EXISTS, before Phase 2 begins. Applied to
both `/verify/stream` and `/batch/stream`.

**How:** A new `fetch_cluster_blocked(cluster_id)` function makes a GET request
to the CourtListener clusters API and returns the `blocked` field value.

**On blocked:**
- Phase 1 verdict remains EXISTS (the citation is real)
- `privacy_protected: true` field added to Phase 1 result
- Phase 2 and Phase 3 are skipped entirely
- UI displays a clear note explaining why

**On API error:** Fail open. If the blocked check fails for any reason
(timeout, network error, unexpected response), Wilson proceeds as if the
opinion is not blocked. It is better to over-verify than to under-verify due
to a transient API issue.

**Performance:** The blocked check adds one extra API call per citation that
passes Phase 1. Timeout is 5 seconds. This adds at most 5 seconds to
Phase 1 in the failure case. In the normal case it adds ~200ms.

**Why fail open:** Wilson's purpose is verification. Blocking verification
due to an uncertain API response would be worse than the alternative. The
blocked flag is a courtesy check, not a security gate.

### What changes

`api.py`:
- New function `fetch_cluster_blocked(cluster_id: int) -> bool`
- `run_pipeline` calls it after Phase 1 EXISTS verdict
- Phase 1 result dict gains `privacy_protected: bool` field

`templates/index.html`:
- `renderPhase1()` checks `privacy_protected` and displays amber notice

### What does not change

- Phase 1 verdict is still EXISTS -- the citation is real
- The blocked check is informational, not a verdict
- FABRICATED and MISATTRIBUTED paths are unaffected -- no point checking
  blocked status on citations that don't exist

### Edge cases

- Cluster returns `blocked: null` or missing field -- treat as False
- Cluster API returns 404 -- treat as False (citation may be in CSV but not API)
- Cluster API returns 429 (rate limit) -- treat as False, log warning
- Network timeout -- treat as False

---

## Improvement 2: Name-Based Lookup Confidence Threshold

### Background

Wilson's Phase 1 has a fallback: if eyecite cannot parse a reporter citation
from the input, Wilson searches CourtListener by name and uses the top result.
This is useful for informal references like "Obergefell v. Hodges" without
a reporter.

The problem: the fallback was proceeding silently even when the top search
result was a poor match for the user's input. A user typing a partial or
incorrect case name could unknowingly verify the wrong case.

### Design

**Threshold:** 60% similarity (rapidfuzz `partial_ratio`) between user input
and the top search result's case name.

- >= 60%: proceed with fallback normally
- < 60%: return a `suggestion` event instead of proceeding

**Why 60%:** This is lower than the MISATTRIBUTED threshold (75%) because
this is a pre-verification nudge in the fallback path, not a verdict threshold.
At 60% there is enough overlap to suggest the right case but not enough to
proceed blindly. At below 60% the match is too speculative.

**The `suggestion` event:**
- Contains the user's original input
- Contains the suggested full citation and case name
- Contains the similarity score
- Does not proceed with verification
- UI offers two actions: "Use this citation" (pre-fills the field) or
  "Start over"

**Why stop rather than warn:** If Wilson proceeded with a low-confidence
fallback and returned EXISTS, the user might accept that verdict without
realizing Wilson verified a different case. A false positive on existence
is worse than a prompt to double-check.

### What changes

`api.py`:
- New constant `FALLBACK_CONFIDENCE_THRESHOLD = 60`
- `run_pipeline` checks similarity before proceeding with fallback
- New `suggestion` event type yielded when threshold not met

`templates/index.html`:
- New `suggestion` event handler renders the "did you mean?" UI
- Two action buttons: use suggested citation or start over

### What does not change

- The fallback itself (name search via CourtListener) is unchanged
- Citations that eyecite parses successfully are unaffected
- The MISATTRIBUTED threshold (75%) is unchanged -- different path

### Edge cases

- User input is a partial name that matches well (>= 60%): proceeds normally
- User input is completely unrelated to any case: < 60%, suggestion shown
- CourtListener name search returns no results: existing UNPARSEABLE path,
  no change needed
- User accepts the suggestion and re-submits the full citation: normal
  eyecite parse path, no fallback triggered

---

## Improvement 3: CSV Update Check Notification

### Background

The bulk citation CSV is a dated snapshot (e.g. citations-2026-03-31.csv).
CourtListener publishes new versions when their database is updated.
Users running Wilson with an old CSV may miss citations added after the
snapshot date.

Wilson should check for updates and notify users, but must not auto-download.
The CSV is 1.9GB uncompressed. Auto-downloading without user consent would
be inappropriate.

### Design

**When:** On server startup, after the CSV loads into memory. The check runs
in a background thread so it does not block startup or the first request.

**How:** Wilson queries the public CourtListener S3 bucket listing for files
matching the `bulk-data/citations-*.csv.bz2` pattern, parses the dates from
filenames, and compares against the current CSV date.

**Result storage:** Two module-level globals:
- `CSV_UPDATE_AVAILABLE: bool` -- True if a newer file exists
- `CSV_LATEST_FILENAME: str | None` -- the filename of the newest available

**Surfaces:**
- `/health` endpoint: `csv_update.available` and `csv_update.latest_filename`
- UI status pill: changes from green to amber when update available
- Tooltip on amber pill: "Update available: {filename}. Re-run setup to update."

**No automatic download.** Wilson informs. The user decides.

**Why S3 listing:** CourtListener publishes bulk data to a public S3 bucket
with predictable naming. The listing is accessible without authentication.
Parsing dates from filenames is reliable and requires no additional API calls.

### What changes

`api.py`:
- New function `parse_csv_date(csv_path: str) -> date | None`
- New function `check_csv_update_available() -> bool`
- New globals `CSV_UPDATE_AVAILABLE` and `CSV_LATEST_FILENAME`
- FastAPI lifespan handler triggers CSV pre-load and update check at startup
- `/health` endpoint gains `csv_update` key
- `index` route passes `csv_update_available` and `csv_latest_filename` to template

`templates/index.html`:
- CSV status pill gains amber state for update available
- Tooltip explains what "update available" means and how to act on it

### What does not change

- The CSV itself is not modified
- No download is triggered automatically
- Wilson functions normally with the existing CSV regardless of update status
- Users without a CSV configured are unaffected (already showing "Not Configured")

### Edge cases

- S3 request times out: `CSV_UPDATE_AVAILABLE` stays False, no error shown
- S3 returns malformed XML: parse error caught, `CSV_UPDATE_AVAILABLE` stays False
- CSV filename has no parseable date: `parse_csv_date` returns None, check skipped
- Current CSV is already the newest: `CSV_UPDATE_AVAILABLE` stays False
- Multiple newer files found: the most recent is reported

---

## Not in scope

- Automatic CSV download
- CSV download progress in the UI
- CourtListener webhook for real-time CSV availability notification
- Notification persistence (if user dismisses the amber pill, it still shows
  on next launch -- no "remind me later" mechanism)

---

## Testing approach

All three improvements are unit-testable with mocked HTTP calls.
No live API calls required in the test suite.

`fetch_cluster_blocked` is tested with mocked responses covering:
blocked=True, blocked=False, missing field, and API error.

`parse_csv_date` is tested with valid filenames, full paths, no-date filenames,
and None input.

`check_csv_update_available` is tested with a mocked S3 response containing
a newer file and one containing only the current file.

Name confidence threshold tests verify the 60% boundary using known case names
with rapidfuzz directly -- no mocking needed since the threshold logic is
a pure calculation.
