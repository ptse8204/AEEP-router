"""Read official registry metadata without pulling or executing image layers."""

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LEADERBOARD_REVISION = "820ee3df9e7227b04f0c60ffe1415aad8a14eebc"
PINNED_TASK_REVISION = "9a1f4dd5f7659f75707435da3ce854b6e48321d1"
LEADERBOARD = ("https://raw.githubusercontent.com/benchflow-ai/"
               f"skillsbench-leaderboard/{LEADERBOARD_REVISION}/")
TASK_SOURCE = "https://raw.githubusercontent.com/benchflow-ai/skillsbench/"
REGISTRY = "https://ghcr.io/v2/benchflow-ai/skillsbench-task-env/"
TASKS = {
    "document-data": ["financial-modeling-qa", "pdf-excel-diff", "sales-pivot-analysis"],
    "software-engineering": [
        "spring-boot-jakarta-migration", "react-performance-debugging",
        "software-dependency-audit",
    ],
}


def read(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1024**2 + 1)
    assert len(raw) <= 1024**2
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


maps = {}
for path in ("prebuilt_images/skillsbench-v1.1.json", "task_sets/skillsbench-v1.1.json",
             "task_sets/skillsbench-v1.1.source.json", "deploy_bundles/skillsbench-v1.1.json"):
    payload = read(LEADERBOARD + path)
    maps[path] = (json.loads(payload), sha(payload))
images = maps["prebuilt_images/skillsbench-v1.1.json"][0]
tasks = {x["task_id"]: x for x in maps["task_sets/skillsbench-v1.1.json"][0]["tasks"]}
task_revision = maps["task_sets/skillsbench-v1.1.source.json"][0]["source_sha"]
deploy_revision = maps["deploy_bundles/skillsbench-v1.1.json"][0]["source_revision"]
registry_read_token = json.loads(read(
    "https://ghcr.io/token?scope=repository%3Abenchflow-ai%2Fskillsbench-task-env%3Apull&service=ghcr.io"
))["token"]
headers = {"Authorization": "Bearer " + registry_read_token, "Accept": ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))}


def manifest(digest):
    raw = read(REGISTRY + "manifests/" + digest, headers)
    assert "sha256:" + sha(raw) == digest
    return json.loads(raw)


pack = ROOT / "reports/toolkit-v2/c13/skillsbench-transport-20261103/task-only-pack.json"
pack_tasks = {x["task_id"]: x for x in json.loads(pack.read_bytes())["tasks"]}
results = []
for domain, names in TASKS.items():
    for name in names:
        reference = images[name]
        index_digest = reference.split("@")[1]
        index = manifest(index_digest)
        platforms = [
            {"digest": entry["digest"], "platform": entry["platform"]}
            for entry in index["manifests"] if entry["platform"]["os"] != "unknown"
        ]
        assert len(platforms) == 1 and platforms[0]["platform"] == {
            "architecture": "amd64", "os": "linux",
        }
        image = manifest(platforms[0]["digest"])
        configuration_digest = image["config"]["digest"]
        raw = read(REGISTRY + "blobs/" + configuration_digest, headers)
        assert "sha256:" + sha(raw) == configuration_digest
        configuration = json.loads(raw)
        assert configuration["os"] == "linux" and configuration["architecture"] == "amd64"
        config = configuration["config"]
        labels = config.get("Labels") or {}
        dockerfile = f"tasks/{name}/environment/Dockerfile"
        pin = next(x for x in pack_tasks[name]["assets"] if x["path"] == dockerfile)
        comparisons = []
        for revision in (task_revision, deploy_revision):
            try:
                digest = sha(read(TASK_SOURCE + revision + "/" + dockerfile))
            except urllib.error.HTTPError as error:
                comparisons.append({"revision": revision, "read_status": error.code})
            else:
                comparisons.append({"revision": revision, "sha256": digest,
                                    "matches_pinned_dockerfile": digest == pin["sha256"]})
        results.append({
            "task_id": name, "domain": domain, "difficulty": tasks[name]["difficulty"],
            "leaderboard_task_digest": tasks[name]["task_digest"], "reference": reference,
            "platform_manifest": platforms[0]["digest"],
            "platform": platforms[0]["platform"], "config_sha256": configuration_digest,
            "compressed_layer_bytes": sum(layer["size"] for layer in image["layers"]),
            "image_source_labels": {k: labels[k] for k in (
                "org.opencontainers.image.source", "org.opencontainers.image.revision",
                "org.opencontainers.image.licenses",
            ) if k in labels},
            "pinned_dockerfile_sha256": pin["sha256"], "dockerfile_comparison": comparisons,
            "asset_equivalence": "UNVERIFIED",
            "operator_license_clearance": "PENDING",
        })
        print(name, results[-1]["compressed_layer_bytes"], comparisons, flush=True)
report = {
    "pinned_task_revision": PINNED_TASK_REVISION,
    "leaderboard_revision": LEADERBOARD_REVISION, "leaderboard_task_source": task_revision,
    "leaderboard_runtime_source": deploy_revision, "source_sha256": {
        path: value[1] for path, value in maps.items()
    },
    "tasks": results, "image_layers_downloaded": 0, "image_runs": 0,
    "model_calls": 0, "comparison_campaigns": "PAUSED",
    "status": "METADATA_ONLY_PENDING_ASSET_EQUIVALENCE_AND_RIGHTS",
}
with (HERE / "runtime-candidates.json").open("x") as output:
    json.dump(report, output, indent=2)
    output.write("\n")
