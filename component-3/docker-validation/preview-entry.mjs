import { spawn } from 'node:child_process';

const backendHost = process.env.BACKEND_HOST ?? '0.0.0.0';
const backendPort = process.env.PORT ?? '3001';
const staticHost = process.env.STATIC_HOST ?? '0.0.0.0';
const staticPort = process.env.STATIC_PORT ?? '8080';

function launch(label, command, args, env) {
  const child = spawn(command, args, {
    env: { ...process.env, ...env },
    stdio: 'inherit',
  });
  child.on('exit', (code, signal) => {
    if (code !== 0 && code !== null) {
      console.error(`${label} exited with code ${code}`);
      process.exit(code);
    }
    if (signal) {
      console.error(`${label} terminated by signal ${signal}`);
      process.exit(1);
    }
  });
  return child;
}

const backend = launch('backend', 'node', ['backend/src/app.js'], {
  HOST: backendHost,
  PORT: backendPort,
});

const staticServer = launch(
  'static-server',
  'node',
  ['/opt/intelise-validator/static-server.mjs'],
  {
    HOST: staticHost,
    PORT: staticPort,
  },
);

function shutdown() {
  backend.kill('SIGTERM');
  staticServer.kill('SIGTERM');
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
