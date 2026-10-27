# Bounded library source review — no subject execution

Ten new repository groups were read as pinned public source data, retaining
3,325,461 bytes. Six archives fit the unchanged limits and need static review;
three exceeded the compressed bound and remain partial/unparsed. One was excluded
by the existing archive safety rules. The combined index now has163 sources,
including133 older records and the preceding20-group metadata sample.

A first named queue stopped before source reads because Gabbi tests lie outside
the current `tests/` contract. A revised queue stopped before source reads because
Absa and Foamlib were already used for development/screening. Their queues/logs
remain. Both are excluded from the final sample, which preserves repository-group
separation. No runtime limit, test assertion or historical evidence was changed.

CrossGL257 and Marshmallow-SQLAlchemy640 were prepared as explicit corrected-
snapshot audits in the adjacent reproduction review. This is a proposal, not a
reproduced case or benchmark result. C++ hooks142 was excluded after code review
found required tests can invoke real pip. No installer was run or mocked away to
obtain a favorable result. Other subjects still need dependency/profile review.
