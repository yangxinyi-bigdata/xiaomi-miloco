/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

export const config = {
  api: {
    target: process.env.VITE_DEV_API_TARGET || 'https://127.0.0.1:8000/',
  },
  app: {
    name: 'Miloco',
    version: '1.0.0'
  }
}

export default config
