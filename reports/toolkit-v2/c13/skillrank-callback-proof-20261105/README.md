# SkillRank core callback proof

The pinned SkillRank core ran its real `run_eval` loop and requested
two isolated fixture runs. AEEP dispatched both through its existing
contained executor and produced protected binary grade certificates.
SkillRank consumed the passing control and the deliberately failing
treatment certificate in the expected order. All four operations
settled. [Results](result.json)

The bridge excludes the upstream numeric defaults from AEEP evidence.
It sends opaque identities and grade certificates. No model ran, no
skill was assessed, and no useful-effect claim follows from these
fixtures. The separate ordinary CLI search/show evidence still applies
at its original scope.

The [exact review](operation-review.json) binds revision
`5216bae9149b4ff8a7f9e014b6889fb094cee8e1`, its unchanged Cargo lock
and vendor tree, and the retained Linux ARM64 compiler image. The
result pins the new binary. The reviewed source overlay adds only
AEEP's [bridge](../../../../integrations/toolkit/skillrank/bridge.rs).
The verified native interface still needs a bounded ordinary CLI
diagnostic using the approved AEEP worker pair.
