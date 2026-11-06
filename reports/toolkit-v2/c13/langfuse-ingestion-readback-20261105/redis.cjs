'use strict';
const dns = require('node:dns').promises;
const net = require('node:net');

async function main() {
  const { REDIS_HOST: host, REDIS_PORT: port, REDIS_AUTH: password } = process.env;
  if (host !== 'redis' || port !== '6379' || !/^[A-Za-z0-9_-]{8,256}$/.test(password || '')) process.exit(2);
  const addresses = (await dns.lookup(host, { all: true })).map((row) => row.address);
  if (addresses.length !== 1 || addresses[0] !== '172.31.248.30') {
    console.log(JSON.stringify({expected_address:false, result:'address_mismatch'}));
    return;
  }
  const result = await new Promise((resolve) => {
    let reply = '';
    const socket = net.createConnection({host, port:Number(port)});
    const finish = (result) => { socket.destroy(); resolve(result); };
    socket.setTimeout(2400, () => finish('timeout'));
    socket.once('error', (error) => finish(error.code || 'socket_error'));
    socket.once('end', () => finish('unexpected_reply'));
    socket.once('connect', () => socket.write('AUTH '+password+'\r\nPING\r\n'));
    socket.on('data', (chunk) => {
      reply += chunk.toString();
      if (reply.length > 128 || reply.startsWith('-')) finish('unexpected_reply');
      else if (reply === '+OK\r\n+PONG\r\n') finish('authenticated_ping');
    });
  });
  console.log(JSON.stringify({expected_address:true, result}));
}

main().catch(() => console.log(JSON.stringify({expected_address:false, result:'lookup_error'})));
