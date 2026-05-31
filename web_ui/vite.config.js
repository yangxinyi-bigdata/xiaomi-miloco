/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

/* eslint-disable no-undef */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path";
import fs from 'fs';
import { config } from './config.js';

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const isDev = command === 'serve';
  const httpsKeyPath = 'certs/localhost-key.pem';
  const httpsCertPath = 'certs/localhost.pem';
  const hasHttpsCerts = fs.existsSync(httpsKeyPath) && fs.existsSync(httpsCertPath);
  
  return {
    plugins: [react()],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['tests/setup/setupTests.js'],
      include: ['tests/**/*.test.{js,jsx,ts,tsx}']
    },
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true
        }
      }
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
        "utils": path.resolve(__dirname, "src/utils"),
        "theme": path.resolve(__dirname, "src/theme"),
      },
      extensions: [".mjs", ".js", ".ts", ".jsx", ".tsx", ".json", ".vue"],
    },
    build: {
      assetsDir: 'assets',
      rollupOptions: {
        output: {
          chunkFileNames: 'assets/js/[name]-[hash].js',
          entryFileNames: 'assets/js/[name]-[hash].js',
          assetFileNames: (assetInfo) => {
            const info = assetInfo.name.split('.');
            const ext = info[info.length - 1];
            if (/\.(css)$/.test(assetInfo.name)) {
              return `assets/css/[name]-[hash].${ext}`;
            }
            if (/\.(png|jpe?g|gif|svg|webp|ico)$/.test(assetInfo.name)) {
              return `assets/images/[name]-[hash].${ext}`;
            }
            if (/\.(woff2?|eot|ttf|otf)$/.test(assetInfo.name)) {
              return `assets/fonts/[name]-[hash].${ext}`;
            }
            // other resource files
            return `assets/[ext]/[name]-[hash].[ext]`;
          }
        }
      }
    },
    server: {
      host: "0.0.0.0",
      // only enable HTTPS in development mode
      ...(isDev && hasHttpsCerts && {
        https: {
          key: fs.readFileSync(httpsKeyPath),
          cert: fs.readFileSync(httpsCertPath)
        }
      }),
      proxy: {
        '/api': {
          target: config.api.target,
          changeOrigin: true,
          ws: true,
          secure: false,
          rewrite: (path) => path.replace(/^\/api/, '')
        }
      }
    }
  };
})
