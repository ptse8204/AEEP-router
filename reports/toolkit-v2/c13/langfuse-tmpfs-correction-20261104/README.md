# Correct the Compose temporary-mount representation

This exact repeat is unstarted and needs operator approval. The prior identity
correction passed actual image checks,then Compose validation failed before any
container startup. All eight tmpfs values have the wrong JSON type. The original
stderr body was not retained; this identified schema defect does not prove it
was the only error.

The new file changes only tmpfs dictionaries into equivalent mount lists. Paths,
options,images,service programs,permissions and all other fields are preserved.
The new driver reuses the same existing task-local keys and preserves both the
failed config and new corrected config. It retains bounded schema paths/error
categories on failure,without raw streams or secret values.

One fresh service/receipt-export/ingestion/disablement attempt is proposed,with
at most63additional operations in the original3200-second/zero-model/$0cash
ceiling. The routine finite amendment changes cumulative operations69to76 to
retain the seven newly charged operations; the existing13charges remain intact.
No compiler,source suite,wheel,docs,pull,build or passed OCI fixture is rerun.
Stop only verified new owned containers;keep images,volumes,network and runtimes.
All old Docker resources,user work and backups remain. Keep50GiB host free.

New first-party static controls verify all eight encodings and unchanged other
fields. They are not actual Compose acceptance or Langfuse ingestion evidence.
[Docker's format](https://docs.docker.com/reference/compose-file/services/#tmpfs)
is the primary contract. No Waza sign-in is needed for this work.
