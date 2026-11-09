# ADR-0009: Trial data and privacy

- **Status:** Proposed
- **Date:** 2026-11-09
- **Depends on:** ADR-0007, ADR-0008
- **Terms:** see `GLOSSARY.md`.

## Context

The trial stores data that didn't exist in phase 1: photos, a record per item
and two Google Sheets. ADR-0007 and ADR-0008 both defer its handling here. The
trial is about 60 items and one staff member, so this ADR sets only the rules
that needs.

It covers trial data only. The catalogue and the eval set stay under CLAUDE.md,
*Private data never enters git*.

## Threat model

ART numbers, Certilogo codes and label photos are already public once a garment
is listed on Street Garms' website; trial items are photographed at intake,
before listing. What's left to protect is the staff member's work record (with
one person in the trial, per-item times and edits identify them), any location
in a photo, and the integrity of the Sheet and the gate's records.

Two threats, most likely first:

1. **Accidental exposure:** a misconfigured bucket, a Sheet shared by link, or
   records pasted into the public repo.
2. **Someone reaching the app who shouldn't:** anyone past the login can confirm
   items, which writes to the main Sheet and adds false records to the gate
   count. ADR-0008, D1 covers this.

Spend is limited by a hard cap on the Anthropic workspace, whoever or whatever
causes it (D5).

Accepted: Anthropic and Google process this data because the service needs them
to. *What's held where* records what each holds and for how long.

Out of scope: a determined attacker targeting this data. Identity-Aware Proxy
and a private bucket are proportionate to this trial.

The catalogue is off, so the trial holds no code-to-product mapping. Replaying
saved reads through the catalogue later (ADR-0007) would create one, and that
output falls under the catalogue's rules.

## What's held where

| Store | Holds | Who can see | Kept for |
|---|---|---|---|
| Postgres on Cloud SQL | One row per item: read, value shown, final value, configuration, times (ADR-0008, D5, D6) | The developer | Deletion date (D1) |
| Postgres backups | Copies of those rows (ADR-0008, D6) | The developer | Deletion date (D1) |
| Cloud Storage bucket | Photos as uploaded, including items never confirmed and failed reads (ADR-0008, D5, D6, D9) | The developer | Deletion date (D1) |
| Main Google Sheet | Final values (ADR-0007) | The developer, the founder and the day-to-day editor, the one staff member | Not deleted: it is the working document |
| Feedback Sheet | Ad-hoc feedback, the hand log, a tab for the downtime log, the trial's start, pause and restart times, and the reason for any sign-off "no"; can hold ART numbers (ADR-0007) | The project team | Deletion date (D1) |
| Failed-trial list, only on a fail | ART numbers only, outside git (D1) | The developer | Until the rerun's gate is read or the project team stops |
| App logs and tracing | What D3 allows | The developer | 30 days |
| Platform logs (Cloud Run) | Request logs. IAP's access logs, which carry the signed-in email, stay off | The developer | 30 days |
| Anthropic API | Every photo, sent for its read | Anthropic | 30 days, or up to 2 years if flagged by its safety systems (its terms, checked 2026-11-09) |

## Decisions

### D1: Access and deletion

Each store's access is named people only, as listed in *What's held where*. App
access is the IAP policy (ADR-0008, D1): the developer, the founder and the
day-to-day editor, the one staff member. Both Sheets are shared with named accounts, never by link, and
that is checked once before the founder review.

Only the developer can reach the technical stores.

Trial data is deleted on a date the project team sets at its stage 3 decision
(ADR-0007), whatever the outcome. Anything labelled for the eval set is copied
there first, and on a fail the date allows for that labelling (ADR-0007). The
developer deletes it and checks the bucket is empty and the Cloud SQL instance
is gone, with retained backups off.

On a fail, before deletion, the developer saves a list of the team trial's ART
numbers (the final values plus the hand log, nothing per item) and keeps it until the
rerun's gate is read or the project team stops (ADR-0007, *Fail*).

The same date covers photos of items never confirmed. The gate needs only their
rows, for the retake total.

**Accepted cost:** if the developer is away, nobody can act on the technical
stores. The instance keeps billing until the deletion date.

### D2: Phone location data in photos

One real upload from the staff member's phone is checked at the founder review. If it carries location,
camera location is turned off on that phone. Nothing changes at the server, so
ADR-0008, D9 still holds.

`upright()` sends an untagged photo byte-for-byte, so any location in it reaches
Anthropic as well as the bucket.

### D3: What logs and tracing may record

Allowlisted fields only: enums, fingerprints, counts and numeric measurements such as latency and input size. No photos and no staff
emails. **observability** follows this.

### D4: ART numbers and Certilogo codes in trial data

These values are public once a garment is listed, so trial stores have no limits
on them beyond ADR-0007's Sheet field, including before listing, and one appearing
in a log or Sheet isn't an incident.

This applies to trial stores only. CLAUDE.md, ADR-0001 and the commit hooks don't
change: codes stay out of git, and the model doesn't return them.

### D5: Secrets and spend

The Anthropic API key and the Google credential for the Sheet are held in Secret
Manager, never in git.

The trial uses its own Anthropic workspace and key, with a monthly spend limit of
$10, set by **deploy** before the founder review. A read refused at the limit is
a failed read (ADR-0007). The developer can raise the limit if it trips by
mistake.

### D6: Google Cloud region

London (`europe-west2`), for Cloud Run, Cloud SQL and the bucket. This sets where
data sits at rest. Every photo still goes to Anthropic for its read.

### D7: Privacy incident

An incident is any of:

- a store readable by someone not on its list
- someone not in the IAP policy reaching the app
- a leaked API key or Google credential
- trial records pasted into the public repo

The developer pauses the trial or the founder review, closes the access or
rotates the key, and treats everything that access could reach as seen. The
project team decides when the pause ends (ADR-0007, *Stop Rule*), and the founder
can't approve the review until it does. Reaching the spend limit isn't an
incident.

**Accepted cost:** IAP access logs are off and items record no user, so a login
by someone not in the IAP policy can't be detected.

## Alternatives considered

- **Threat model, two classes of data or a rating per store:** rejected. With
  label photos and codes public, the classes wouldn't lead to different rules.
- **Threat model, staff overuse as its own threat:** rejected. Phase 1 reads cost
  about $0.012 each (`evals/BASELINES.md`), so one person can't reach a meaningful
  cost through normal use, and the spend limit covers a fault.
- **D1, a named backup person for the technical stores:** rejected. It adds a
  second person with access to the staff member's work record.
- **D1, a fixed period after the trial or the decision (30 or 90 days):**
  rejected. What phase 3 needs from this data isn't known until the decision.
- **D1, no date until phase 3 is decided:** rejected. Phase 3 never comes if the
  project team stops after a fail, so nothing would be deleted.
- **D1, IAP access logs on:** rejected. They would only help in an unlikely
  incident, and D7 already treats everything an access could reach as seen.
- **D2, stripping location at the server:** rejected. It conflicts with ADR-0008,
  D9, which requires the stored photo to be the upload as received.
- **D4, keeping codes sensitive in trial stores:** rejected. It would make a
  public value appearing in a Sheet an incident.
- **D5, a spend limit on the whole account:** rejected. A trial fault could stop
  paid eval runs, and the limit would have to be high enough for them too.
- **D6, Belgium or a US region:** rejected. Staff uploads are closest to London.

## Consequences

- **deploy** uses London, creates the Anthropic workspace, key and spend limit,
  puts both credentials in Secret Manager, leaves IAP access logs off and checks
  the Sheet sharing, all before the founder review.
- **observability** records only what D3 allows.
- The founder review includes D2's check.
- The project team's stage 3 decision also sets the deletion date.
- ADR-0007's *Stop Rule* uses D7's definition.
- The downtime log is a tab in the feedback Sheet.
