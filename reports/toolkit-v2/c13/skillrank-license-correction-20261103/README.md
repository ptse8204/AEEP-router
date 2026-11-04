# Complete the unstarted SkillRank runtime check

The corrected AEEP wheel and all72 offline documentation inputs passed under
review`d6fbbad3`. Keep those results and retained runtimes. The runtime component
stopped while inspecting its first verified source archive, before the Rust image
pull, compilation, registry startup or any upstream executable.

The fault is in the first-party license guard: it rejected the complete expression
`0BSD OR MIT OR Apache-2.0` even though the archive offers the already accepted
MIT and Apache alternatives. The separate inventory also needs to acknowledge
the certificate-data license. This is not an upstream build failure or an
architecture decision.

The [public registry audit](registry-metadata-audit.json) checked all86 versions
against their locked archive checksums. It found15 exact license expressions and
14,677,290 declared compressed bytes. Those metadata claims are not archive
verification: the new guard requires each actual archive manifest to match its
reviewed expression before any compiler runs. Source/license files remain local;
redistribution and release remain outside scope. Two first-party data controls
accepted the unchanged Adler archive and rejected an altered license expectation.
No code from that archive ran.

The proposed runtime-only continuation keeps the original grant and its limits:
40operations,4,500seconds,zero models and $0cash authority. Two operations and
2.7450645421631634seconds remain charged. It reuses the already verified Adler
archive, fetches only the85 unstarted archives, then performs the same single
image pull, offline build, real upstream search/show and containment/stop checks.
No package/docs rerun, new dependency version, image change, credential access,
release or deletion of existing resources is proposed. The normal50GiB reserve
and8GiB runtime start headroom remain.

The coordinator uses the exact retained e48eec5f source snapshot. This lets
independent implementation continue without silently changing the checked runtime.
The existing expiry may be extended through the recorded finite-amendment path;
ceilings and counters cannot reset. All partial downloads, failed receipts and
earlier results remain. Only newly owned check containers may be stopped/removed
after verifying their IDs,image and ownership label.

After applicable exact approval, inspect started/result markers, then run
`run-runtime.py --execute-approved REVIEW_SHA256` once from this directory. No
automatic software replacement or replay is implied. This checks build/search/show;
the bounded SkillRank callback, ordinary workflow integration and all-stack gate
still remain open. Comparisons remain paused.
