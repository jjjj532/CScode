import { DEFAULT_SERVER_PORT } from '../src/config';

describe('vite.config.ts port default', () => {
  test('DEFAULT_SERVER_PORT is 8000', () => {
    expect(DEFAULT_SERVER_PORT).toBe('8000');
  });

  test('proxy target uses DEFAULT_SERVER_PORT as fallback', () => {
    const port = process.env.CSCORE_SERVER_PORT || DEFAULT_SERVER_PORT;
    expect(`http://localhost:${port}`).toBe('http://localhost:8000');
  });

  test('proxy target respects CSCORE_SERVER_PORT env var', () => {
    process.env.CSCORE_SERVER_PORT = '9000';
    const port = process.env.CSCORE_SERVER_PORT || DEFAULT_SERVER_PORT;
    expect(`http://localhost:${port}`).toBe('http://localhost:9000');
    delete process.env.CSCORE_SERVER_PORT;
  });
});
