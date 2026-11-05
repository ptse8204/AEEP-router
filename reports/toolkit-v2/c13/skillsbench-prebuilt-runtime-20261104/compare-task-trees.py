"""Check tree drift across the pinned pack and the published image-source refs."""

import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = "https://api.github.com/repos/benchflow-ai/skillsbench/git/trees/"
runtime = json.loads((HERE / "runtime-candidates.json").read_bytes())
requests = {}


def tree(revision, recursive=False):
    url = INDEX + revision + ("?recursive=1" if recursive else "")
    request = urllib.request.Request(url, headers={
        "User-Agent": "AEEP-source-review", "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1024**2 + 1)
    assert len(raw) <= 1024**2
    value = json.loads(raw)
    assert not value.get("truncated")
    requests[url] = hashlib.sha256(raw).hexdigest()
    return {row["path"]: row for row in value["tree"]}


refs = (runtime["pinned_task_revision"], runtime["leaderboard_task_source"],
        runtime["leaderboard_runtime_source"])
roots = [tree(tree(rev)["tasks"]["sha"]) for rev in refs]
results = []
for task in runtime["tasks"]:
    name = task["task_id"]
    task_roots = [root[name]["sha"] for root in roots]
    assert task_roots[1] == task_roots[2], name
    earlier, later = (tree(t, True) for t in task_roots[:2])
    changes = []
    for path in sorted(set(earlier) | set(later)):
        old = earlier.get(path, {})
        new = later.get(path, {})
        if "blob" not in (old.get("type"), new.get("type")):
            continue
        if (old.get("sha"), old.get("mode")) == (new.get("sha"), new.get("mode")):
            continue
        changes.append({"path": path, "pinned_git_blob": old.get("sha"),
                        "image_source_git_blob": new.get("sha"),
                        "pinned_mode": old.get("mode"), "image_source_mode": new.get("mode")})
    environment_changes = [x for x in changes if x["path"].startswith("environment/")
                           and not x["path"].startswith("environment/skills/")]
    protected_changes = [x for x in changes if x["path"].startswith(("oracle/", "verifier/"))]
    result = {"task_id": name, "pinned_tree": task_roots[0], "image_source_tree": task_roots[1],
              "published_refs_agree": True, "changes": changes,
              "non_skill_environment_paths_match": not environment_changes,
              "protected_program_paths_match": not protected_changes}
    print(name, len(changes), len(environment_changes), len(protected_changes), flush=True)
    results.append(result)

with (HERE / "task-tree-audit.json").open("x") as out:
    json.dump({"refs": refs, "response_sha256": requests, "tasks": results,
               "images_pulled": 0, "upstream_programs_executed": 0,
               "asset_equivalence_scope": "Git blob and file-mode comparison only. Image layers, embedded downloads and licenses remain unverified."},
              out, indent=2)
    out.write("\n")
