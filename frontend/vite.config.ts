import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const rawBackend = (env.VITE_API_BASE ?? 'http://127.0.0.1:8000').trim() || 'http://127.0.0.1:8000';
  const normalizedBackend = rawBackend.replace(/\/$/, '');
  const backendBase = normalizedBackend.endsWith('/api') ? normalizedBackend.replace(/\/api$/, '') : normalizedBackend;
  const wsBase = backendBase.replace(/^http/, 'ws');

  return {
    server: {
      port: 4173,
      open: true,
      proxy: {
        '/api': {
          target: backendBase,
          changeOrigin: true,
        },
        '/ws': {
          target: wsBase,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    preview: {
      proxy: {
        '/api': {
          target: backendBase,
          changeOrigin: true,
        },
        '/ws': {
          target: wsBase,
          changeOrigin: true,
          ws: true,
        },
      },
    },
  };
});
