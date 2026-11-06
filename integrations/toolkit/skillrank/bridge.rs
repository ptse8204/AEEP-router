//! Run the pinned upstream SkillRank engine over canonical AEEP trial slots.
//! Only opaque identities and settled grade certificates cross this boundary.

use serde::Deserialize;
use serde_json::json;
use skillrank_core::runner::{
    run_eval, AgentRunner, Config, FixtureProvider, Isolation, PreparedWorkspace, RunOutcome,
    RunSpec, Verdict, Verifier,
};
use skillrank_core::types::{ResolveResponse, Suite, SuiteTask};
use std::cell::{Cell, RefCell};
use std::fs::File;
use std::io::{self, ErrorKind, Read, Write};
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

const MAX_FRAME: u64 = 8192;
const ARMS: [&str; 2] = ["control", "treatment"];
#[cfg(target_os = "macos")]
const RESPONSES: &str = "responses";
#[cfg(not(target_os = "macos"))]
const RESPONSES: &str = "/responses";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    case_id: String,
    skill_slug: String,
    skill_sha256: String,
    run_token: String,
    timeout_seconds: u32,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Certificate {
    run_token: String,
    case_id: String,
    arm: String,
    trial_ref: String,
    canonical_valid: bool,
}

fn identity(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value.bytes().all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
}

fn digest(value: &str) -> bool {
    value.len() == 64
        && value.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn frame(reader: impl Read) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    reader
        .take(MAX_FRAME + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "could not read bounded frame")?;
    if bytes.len() as u64 > MAX_FRAME {
        return Err("frame exceeds its limit".into());
    }
    Ok(bytes)
}

fn emit(value: serde_json::Value) -> Result<(), String> {
    let mut stdout = io::stdout().lock();
    writeln!(stdout, "{value}")
        .and_then(|_| stdout.flush())
        .map_err(|_| "could not emit bounded frame".into())
}

struct Bridge {
    request: Request,
    next: Cell<usize>,
    pending: RefCell<Option<Certificate>>,
    verified: Cell<usize>,
}

impl Bridge {
    fn certificate(&self, arm: &str) -> Result<Certificate, String> {
        // The reviewed launcher makes the parent the sole writer.
        let path = Path::new(RESPONSES).join(format!("{arm}.json"));
        let deadline = Instant::now() + Duration::from_secs(u64::from(self.request.timeout_seconds));
        loop {
            match File::open(&path) {
                Ok(file) => {
                    let value: Certificate = serde_json::from_slice(&frame(file)?)
                        .map_err(|_| "invalid grade certificate")?;
                    if value.run_token != self.request.run_token
                        || value.case_id != self.request.case_id
                        || value.arm != arm
                        || !digest(&value.trial_ref)
                    {
                        return Err("grade certificate differs from selected slot".into());
                    }
                    return Ok(value);
                }
                Err(error) if error.kind() == ErrorKind::NotFound && Instant::now() < deadline => {
                    thread::sleep(Duration::from_millis(25));
                }
                Err(_) => return Err("canonical grade certificate unavailable".into()),
            }
        }
    }
}

impl FixtureProvider for Bridge {
    fn prepare(&self, task_id: &str) -> Result<PreparedWorkspace, String> {
        if task_id != self.request.case_id {
            return Err("unreviewed fixture slot".into());
        }
        Ok(PreparedWorkspace { path: PathBuf::from(RESPONSES), cleanup_root: None })
    }

    fn isolation(&self) -> Isolation {
        // Worker containment lives in AEEP receipts, never a native SkillRank attestation.
        Isolation::Worktree
    }
}

impl AgentRunner for Bridge {
    fn agent_name(&self) -> String {
        "aeep-controlled".into()
    }

    fn agent_version_band(&self) -> String {
        "opaque-callback-v1".into()
    }

    fn run_task(&self, spec: &RunSpec) -> Result<RunOutcome, String> {
        let arm = ARMS.get(self.next.get()).ok_or("unreviewed trial")?;
        if spec.working_dir != Path::new(RESPONSES)
            || spec.instruction != self.request.case_id
            || spec.skill_slug != self.request.skill_slug
            || spec.skill_installed != (*arm == "treatment")
            || !spec.skill_content.is_empty()
            || spec.timeout_sec != self.request.timeout_seconds
            || self.pending.borrow().is_some()
        {
            return Err("upstream changed the reviewed slot or arm".into());
        }
        emit(json!({"kind":"trial","run_token":self.request.run_token,
                    "case_id":self.request.case_id,"arm":arm}))?;
        let certificate = self.certificate(arm)?;
        let trial_ref = certificate.trial_ref.clone();
        self.pending.replace(Some(certificate));
        self.next.set(self.next.get() + 1);
        // Upstream requires numeric defaults. The bridge never exports them.
        Ok(RunOutcome { trajectory_digest: trial_ref, ..RunOutcome::default() })
    }
}

impl Verifier for Bridge {
    fn verify(&self, working_dir: &Path, task_id: &str) -> Result<Verdict, String> {
        let certificate = self.pending.take().ok_or("grade certificate was not dispatched")?;
        if working_dir != Path::new(RESPONSES) || task_id != certificate.case_id {
            return Err("upstream verifier changed the selected slot".into());
        }
        self.verified.set(self.verified.get() + 1);
        Ok(Verdict { pass: certificate.canonical_valid, verifier_error: false })
    }
}

fn run() -> Result<(), String> {
    let request: Request = serde_json::from_slice(&frame(io::stdin().lock())?)
        .map_err(|_| "invalid scheduler request")?;
    if !identity(&request.case_id) || !identity(&request.skill_slug)
        || !digest(&request.skill_sha256) || !digest(&request.run_token)
        || !(1..=60).contains(&request.timeout_seconds)
    {
        return Err("request outside reviewed envelope".into());
    }
    let bridge = Bridge { request, next: Cell::new(0), pending: RefCell::new(None), verified: Cell::new(0) };
    let suite = Suite {
        id: "aeep-controlled-diagnostic".into(), version: "1".into(),
        tasks: vec![SuiteTask {
            id: bridge.request.case_id.clone(), instruction: bridge.request.case_id.clone(),
            timeout_sec: i64::from(bridge.request.timeout_seconds), ..SuiteTask::default()
        }],
        ..Suite::default()
    };
    let skill: ResolveResponse = serde_json::from_value(json!({
        "slug": bridge.request.skill_slug, "version": "local-reviewed", "source_type": "local",
        "content_hash": bridge.request.skill_sha256, "scan_tier": "unknown"
    })).map_err(|_| "invalid reviewed skill identity")?;
    let config = Config { trials: 1, model: "aeep-controlled".into(), artifacts_dir: None };
    let result = run_eval(&suite, &skill, &config, &bridge, &bridge, &bridge)?;
    if result.conforming || result.bundle.trials.len() != ARMS.len()
        || bridge.verified.get() != ARMS.len() || bridge.pending.borrow().is_some()
    {
        return Err("incomplete or unreviewed SkillRank completion".into());
    }
    let rows: Result<Vec<_>, _> = result.bundle.trials.iter().zip(ARMS).map(|(trial, arm)| {
        if trial.task_id != bridge.request.case_id || trial.arm.as_str() != arm
            || !matches!(trial.verdict.as_str(), "pass" | "fail") || !digest(&trial.trajectory_digest)
        {
            return Err("upstream trial output differs");
        }
        Ok(json!({"arm":arm,"trial_ref":trial.trajectory_digest,"canonical_valid":trial.verdict=="pass"}))
    }).collect();
    emit(json!({"kind":"done","run_token":bridge.request.run_token,
                "harness":result.bundle.harness.name,"harness_version":result.bundle.harness.version,
                "trials":rows?,"upstream_numeric_fields_excluded":true}))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("SkillRank diagnostic stopped: {error}");
        std::process::exit(2);
    }
}
