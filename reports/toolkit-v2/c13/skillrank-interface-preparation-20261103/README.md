# SkillRank core integration boundary

The pinned core exposes the interfaces needed for controlled evaluation. Reuse
its `AgentRunner`, `FixtureProvider` and `Verifier` callbacks to call AEEP's
approved executors and protected graders. Its stock runner spawns the host agent
and therefore cannot establish AEEP worker isolation. A stub or imported result
also cannot close functional integration.

The [source inspection](inspection.json) verifies twelve exact Git blobs at
revision `5216bae9149b4ff8a7f9e014b6889fb094cee8e1`. Package version0.1.5 and
runner label0.1.0 are distinct. These files are staged privately; none ran.

Search/show use anonymous GETs. The MIT CLI includes a local registry server,
with a loopback default and an explicit catalog option. That can supply actual
client/server checks without implementing another registry or deploying the
separate Elastic-2.0 registry/web service. Use reviewed repository-authored
catalog data; upstream seed entries do not establish candidate safety or rights.
See the pinned [client](https://github.com/buildbetter-app/skillrank/blob/5216bae9149b4ff8a7f9e014b6889fb094cee8e1/crates/skillrank-core/src/client.rs),
[server](https://github.com/buildbetter-app/skillrank/blob/5216bae9149b4ff8a7f9e014b6889fb094cee8e1/crates/skillrank/src/serve.rs),
and [license](https://github.com/buildbetter-app/skillrank/blob/5216bae9149b4ff8a7f9e014b6889fb094cee8e1/LICENSE).

The [upstream runner](https://github.com/buildbetter-app/skillrank/blob/5216bae9149b4ff8a7f9e014b6889fb094cee8e1/crates/skillrank-core/src/runner/mod.rs)
forces skill use for its treatment. That is suitable for the required bounded
content diagnostic, not optional-use value evidence. Preserve AEEP's complete
source/binary identity alongside upstream version bands. Retain actual raw token
categories; compatibility defaults cannot become observed usage or savings.

Remaining work is concrete: implement the thin callback bridge, review its
compiler/runtime closure, stage exact artifacts and prepare a bounded build,
service and execution review. Cargo.lock lists86 registry packages; none has an
exact verified match in the current Cargo cache. No global setup, login,
installer, update, model, service or publication was performed. This is source
preparation, not a working SkillRank integration or acceptance pass.
