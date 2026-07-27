/**
 * Logger Tests
 */
import { createLogger, setLogLevel, LogLevel, getLogLevel } from '../src/lib/logger';

describe('createLogger', () => {
  const originalEnv = process.env.NODE_ENV;

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    setLogLevel(LogLevel.DEBUG);
  });

  test('returns a logger with debug/info/warn/error methods', () => {
    const logger = createLogger('test');
    expect(typeof logger.debug).toBe('function');
    expect(typeof logger.info).toBe('function');
    expect(typeof logger.warn).toBe('function');
    expect(typeof logger.error).toBe('function');
  });

  test('debug suppressed at INFO', () => {
    const logger = createLogger('test');
    const spy = jest.spyOn(console, 'debug').mockImplementation(() => {});
    setLogLevel(LogLevel.INFO);
    logger.debug('should not appear');
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  test('info messages are shown at INFO level', () => {
    const logger = createLogger('test');
    const spy = jest.spyOn(console, 'info').mockImplementation(() => {});
    setLogLevel(LogLevel.INFO);
    logger.info('should appear');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  test('warn messages are shown at WARN level', () => {
    const logger = createLogger('test');
    const spy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    setLogLevel(LogLevel.WARN);
    logger.warn('warning');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  test('info messages are suppressed at WARN level', () => {
    const logger = createLogger('test');
    const spy = jest.spyOn(console, 'info').mockImplementation(() => {});
    setLogLevel(LogLevel.WARN);
    logger.info('should not appear');
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  test('error messages always appear', () => {
    const logger = createLogger('test');
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    setLogLevel(LogLevel.ERROR);
    logger.error('error');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  test('includes module prefix in output', () => {
    const logger = createLogger('Sidebar');
    const spy = jest.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('hello');
    expect(spy).toHaveBeenCalledWith('[Sidebar]', 'hello');
    spy.mockRestore();
  });

  test('passes extra args to console', () => {
    const logger = createLogger('test');
    const spy = jest.spyOn(console, 'info').mockImplementation(() => {});
    logger.info('fetch done', { id: 1 }, 'extra');
    expect(spy).toHaveBeenCalledWith('[test]', 'fetch done', { id: 1 }, 'extra');
    spy.mockRestore();
  });

  test('default level is INFO in production', () => {
    process.env.NODE_ENV = 'production';
    jest.resetModules();
    const prodLogger = require('../src/lib/logger');
    expect(prodLogger.getLogLevel()).toBe(prodLogger.LogLevel.INFO);
    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });

  test('debug is suppressed in production', () => {
    process.env.NODE_ENV = 'production';
    jest.resetModules();
    const prodLogger = require('../src/lib/logger');
    const logger = prodLogger.createLogger('test');
    const spy = jest.spyOn(console, 'debug').mockImplementation(() => {});
    logger.debug('noisy');
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });

  test('error is visible in production', () => {
    process.env.NODE_ENV = 'production';
    jest.resetModules();
    const prodLogger = require('../src/lib/logger');
    const logger = prodLogger.createLogger('test');
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    logger.error('crash');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });
});
