# Native Waza backend preparation

The retained public artifacts and native Copilot bootstrap checks passed. A real
Waza evaluation is still blocked on protected operator sign-in, account access,
and a bounded backend execution/disclosure review. Comparisons remain paused.

- Data pipeline `b9897f6b`: two exact publisher-hash archives, 157,492,008 response
  bytes and 252,223,745 extracted bytes across three regular files. No archived
  program executed during acquisition. These are body counts, not wire traffic.
- Native pipeline `87cc0c41`: denied unrelated read/write and networking; Waza
  static Go build metadata; actual Copilot 1.0.85 version/help. All four checks
  passed, with no models, authentication, Docker changes or Waza guest execution.
- Waza embeds selected commit e534d149 but reports vcs.modified=true and
  v0.38.9+dirty. Publisher release/hash provenance is established; exact clean
  source-to-binary reproducibility is not.
- The canonical ledger settled 2 operations/6.269825874827802seconds for acquisition
  and 5 operations/3.513753082603216seconds for native checks. No outstanding
  reservations. Wrapper intervals exclude nested commands. CPU, memory, cash and
  wire-byte measurements remain unknown;0cash authority is not a savings claim.
- Source/license/preparation work outside these intervals is NOT_RECORDED. All
  archives, binaries, runtime files, synthetic canary and receipts remain. No
  existing user, backup or Docker resource was removed.

[Source provenance](source-provenance.json) retains public release, license and
account-documentation references. The [operator setup](OPERATOR_SETUP.md) provides
one concrete terminal-only login action. Its helper is unexecuted, the credential
area does not exist, and its one-operation grant is unapplied. Never inspect that
area after sign-in or capture provider output through agent tools.

No passed source, wheel, docs or old Waza mock check was replayed. This is backend
preparation, not stack integration, candidate usefulness, selection usefulness,
resource acceptance or release evidence. Main product source 5a13a630 is unchanged.
