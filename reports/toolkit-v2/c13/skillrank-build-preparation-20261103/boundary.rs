// First-party engineering probe. No task data, model or credential access.
use std::fs::{self, OpenOptions};
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

fn main() {
    let host_canary = std::env::args().nth(1).expect("reviewed host canary path");
    let host_read_denied = fs::read(&host_canary).is_err();
    let root_write_denied = OpenOptions::new().create_new(true).write(true)
        .open("/aeep-outside-write-canary").is_err();
    let docker_socket_absent = fs::metadata("/var/run/docker.sock").is_err();
    let outside: SocketAddr = "1.1.1.1:443".parse().unwrap();
    let external_network_denied = TcpStream::connect_timeout(&outside, Duration::from_secs(1)).is_err();
    let local: SocketAddr = "127.0.0.1:18899".parse().unwrap();
    let selected_loopback_available = TcpStream::connect_timeout(&local, Duration::from_secs(1)).is_ok();
    fs::write("/work/probe-owned", b"owned boundary output").expect("owned workspace write");
    let passed = host_read_denied && root_write_denied && docker_socket_absent
        && external_network_denied && selected_loopback_available;
    println!("{{\"passed\":{passed},\"host_read_denied\":{host_read_denied},\"root_write_denied\":{root_write_denied},\"docker_socket_absent\":{docker_socket_absent},\"external_network_denied\":{external_network_denied},\"selected_loopback_available\":{selected_loopback_available}}}");
    if !passed { std::process::exit(1); }
}
