'use strict';
const net = require('node:net');
const dns = require('node:dns').promises;

function ping(host) {
  return new Promise((resolve) => {
    let received = '';
    let settled = false;
    const socket = net.createConnection({ host, port: 6379 });
    const finish = (value) => {
      if (!settled) {
        settled = true;
        socket.destroy();
        resolve(value);
      }
    };
    socket.setTimeout(1800, () => finish('timeout'));
    socket.once('error', (error) => finish(error.code || 'socket_error'));
    socket.once('end', () => finish('unexpected_reply'));
    socket.once('connect', () => socket.write('AUTH aeep-public-fixture\r\nPING\r\n'));
    socket.on('data', (chunk) => {
      received += chunk.toString();
      if (received.length > 128 || received.startsWith('-')) finish('unexpected_reply');
      else if (received === '+OK\r\n+PONG\r\n') finish('authenticated_ping');
    });
  });
}

async function main() {
  const [staticIp, dynamicIp] = process.argv.slice(1);
  const endpoints = {
    static_ip: staticIp,
    static_dns: 'aeep-redis-static',
    static_hosts_entry: 'redis',
    dynamic_ip: dynamicIp,
    dynamic_dns: 'aeep-redis-dynamic'
  };
  const cases = await Promise.all(Object.entries(endpoints).map(async ([label, host]) => {
    let addresses = [];
    try { addresses = (await dns.lookup(host, { all: true })).map((row) => row.address); } catch {}
    return [label, { addresses, result: await ping(host) }];
  }));
  console.log(JSON.stringify(Object.fromEntries(cases)));
}

main().catch(() => process.exit(2));
