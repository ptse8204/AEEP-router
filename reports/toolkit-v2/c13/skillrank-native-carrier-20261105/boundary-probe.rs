// First-party probe. This binary has no SkillRank or external dependencies.
use std::{env, fs, net::TcpListener, path::Path, process::Command};

fn main() {
    let outside = env::args().nth(1).expect("synthetic outside file");
    let certificate = Path::new("responses/control.json");
    assert_eq!(fs::read(certificate).unwrap(), b"parent-owned certificate\n");
    assert!(fs::write(certificate, b"forged").is_err());
    assert!(fs::write("responses/new.json", b"forged").is_err());
    assert!(fs::read(outside).is_err());
    assert!(TcpListener::bind(("127.0.0.1", 0)).is_err());
    assert!(Command::new("/usr/bin/true").status().is_err());
    println!("certificate read, file writes, unrelated read, network and child exec: pass");
}
