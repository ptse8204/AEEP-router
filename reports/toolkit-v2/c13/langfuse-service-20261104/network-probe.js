// Fixed engineering probe: no model, shell, data upload, or host file access.
const net = require('node:net');
const socket = net.connect({host: '1.1.1.1', port: 443});
let done = false;
function finish(denied) {
  if (done) return;
  done = true;
  socket.destroy();
  process.stdout.write(JSON.stringify({external_connect_denied: denied}));
  process.exitCode = denied ? 0 : 1;
}
socket.setTimeout(2000, () => finish(true));
socket.on('error', () => finish(true));
socket.on('connect', () => finish(false));
