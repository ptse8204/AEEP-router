# Two cached repository subjects — pending execution review

This batch tests conservative native-name expansion on two cached public
snapshots: **asottile/dead issue 204** and **nhairs/python-json-logger issue 39**.
It uses the existing AEEP ledger/container executor and pytest hooks. It adds
no core code, image, service or installed package.

The original three-subject draft is withdrawn before execution. Sopel's source
requires SQLAlchemy `>=1.4,<1.5`, while the retained image has 2.0.44; its source
also requires installed Sopel distribution metadata. Those are concrete runtime
blockers, not an architecture decision. Sopel is excluded from this review.

| Component | Exact finite scope |
| --- | --- |
| New source subjects | Dead: 32 published aliases; JSON logging: 163 aliases. Original source/test/repair bytes and licenses pinned |
| Scope method | Collect full native names, then require every exact/first-token parameter match. Reject missing, overlapping, conflicting, invalid or oversized groups. Freeze all derived truth/selector/payload hashes before body trials |
| Default observer | Four fresh boundary/state/transport probes, two event fixtures and one derived reference, chosen by lexical case ID before body outcomes |
| Runtime support | One probe; exact cached Identify 2.6.15 ZIP loaded privately, plus inherited orjson/msgspec/freezegun versions checked. No installation |
| Subject trials | Two collection calls and four reference/original body calls; all expanded tests required and frozen semantic-negative outcomes checked |
| Documentation | Same cached pinned Lychee 0.24.2 and markdownlint 0.23.3, 69 active documents, offline |

Initial maximum: 14 calls, 16 existing-grant operations and 640 reserved seconds.
With two optional immutable-payload control calls and one additional setup/analysis
phase, the cumulative ceiling is **16 calls, 20 operations and 860 reserved
seconds**. These are execution allowances, not product resource requirements.
No automatic retry, uncertain replay, grant refund or budget reset is allowed.

Use retained image `9f473c49` only. No downloads, builds/pulls/image deletion,
installations, models, cash, credentials, new services/destinations, activation
or release. Keep 50 GiB free and all images. Remove only new owned containers,
unchanged canary and unchanged private docs-checker runtime; retain evidence.

The new expanded scopes are explicitly authored, not official benchmark scores
or retrospective fixes to old results. Collection supplies no passing test
evidence. References must pass every required identity; originals must expose
the declared bug while preservation checks pass. Model outcomes never influence
scope. A failed case stays excluded and independent cases continue after known
completion/cleanup. Common authority/accounting/identity/cleanup uncertainty
stops dispatch.

Preparation passed 16 data-only scope checks, actual collector fixtures with
external dispatch replaced, canonical definition/budget guards and source/license/
image-ancestry checks. No new source or Identify code has run. The current
source's 13 gates and wheel's 20 installed checks are reused unchanged.

The pool remains **63 snapshots**, with **78 cases missing**. Neither staged
subject counts until actual reproduction passes. Qualification, comparative
usefulness, selection, resource acceptance, human controls and release stay open.
