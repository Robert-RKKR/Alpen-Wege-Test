# List endpoints: filters and sorting - decisions

Scope: the 33 list endpoints (GET of a collection) only. Single-object GETs, POST, PATCH, DELETE are not changed. No database change.

Plan: `get_filters_implementation_plan.md` (v2, 2026-10-26). Tools and tests: `filters_tools/`. **Status 2026-10-26: DELIVERED to the repo; not yet deployed on your host.**

## Decided by you (2026-10-26)

1. **Paging stays as it is:** default `limit` 1000 where it is 1000 today (100 on tracks, event log, jobs, my jobs), the maximum as today (none, except 500 on tracks, jobs and my jobs), `offset` as before (`skip` on the users list). Only filters and `sort` are new.
2. **Unknown parameters stay ignored.** Only the values that make the database fail answer `422` instead of `500`: `limit` or `offset` below the minimum or above 1,000,000,000, numbers and dates out of range, a NUL character.

## Answered 2026-10-26: implement the proposal = all recommended (gzip included)

Host step is yours: the commands of plan section 6.6 (expect 506 files before, 507 after, name hash `59a0472fc22afb1b`, content hash `ed98da707669c12f`, pytest 223, `list_check.py` 907 with `--gzip`).

## The questions as they were asked (plan section 2), with my recommendations

| # | Question | Recommendation |
|---|---|---|
| 1 | Filter set per endpoint (plan section 4) | as in section 4 |
| 2 | Text search `q` | ILIKE over the names (3 languages) and a few other columns, at least 2 characters |
| 3 | gzip compression (off unless you say yes) | yes, if your proxy does not already compress (1.2 MB page becomes 83 KB) |
| 4 | `sort=name` / `sort=-name` | include |
| 5 | Map filters `bbox` (POIs, regions) and `near` + `radius_m` (POIs) | include |
| 6 | Paging style | keep limit/offset with a total |
| 7 | `UserService.list_users` (now unused) | keep |
| 8 | Does your host already run the Phase 3 layout? (still open from `?expand=`) | tell me |

## Verified facts

- Your data: 20,758 POIs (1.2 KB a row), 1,570 regions, 250 countries. A page of 1000 POIs: 1.2 MB, 150 ms; no index needed today (slowest filtered page 49 ms).
- A negative `limit` or `offset` answered 500 today; `GET /management/jobs` without parameters answered 500 (fixed by the rewrite).
- Tested: 223 unit tests, 903 live checks, three library stacks, 39 deliberate mistakes all caught, Newman before and after the same, one independent review (first version; findings fixed).
