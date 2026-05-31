/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import '@testing-library/jest-dom';
import 'whatwg-fetch';
import { afterAll, afterEach, beforeAll } from 'vitest';

let server;

if (typeof window !== 'undefined' && (
  !window.localStorage ||
  typeof window.localStorage.getItem !== 'function'
)) {
  const storage = new Map();
  const localStorageMock = {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
    clear: () => storage.clear(),
  };
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: localStorageMock,
  });
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: localStorageMock,
  });
}

// Establish API mocking before all tests.
beforeAll(async () => {
  ({ server } = await import('../mocks/server'));
  server.listen({ onUnhandledRequest: 'error' });
});

// Reset any request handlers that are declared as a part of our tests
// (i.e. for testing one-time error scenarios)
afterEach(() => {
  server.resetHandlers();
});

// Clean up after the tests are finished.
afterAll(() => {
  server.close();
});


if (typeof window !== 'undefined' && !window.getComputedStyle) {
  Object.defineProperty(window, 'getComputedStyle', {
    configurable: true,
    writable: true,
    value: () => ({
      getPropertyValue: () => '',
    }),
  });
}

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => { },
      removeListener: () => { },
      addEventListener: () => { },
      removeEventListener: () => { },
      dispatchEvent: () => false,
    }),
  });
}
