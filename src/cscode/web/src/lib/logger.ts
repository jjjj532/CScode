export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  SILENT = 4,
}

let currentLevel: LogLevel =
  process.env.NODE_ENV === 'production' ? LogLevel.INFO : LogLevel.DEBUG;

export function setLogLevel(level: LogLevel): void {
  currentLevel = level;
}

export function getLogLevel(): LogLevel {
  return currentLevel;
}

export interface Logger {
  debug: (msg: string, ...args: unknown[]) => void;
  info: (msg: string, ...args: unknown[]) => void;
  warn: (msg: string, ...args: unknown[]) => void;
  error: (msg: string, ...args: unknown[]) => void;
}

const consoleMethods: Record<number, keyof Console> = {
  [LogLevel.DEBUG]: 'debug',
  [LogLevel.INFO]: 'info',
  [LogLevel.WARN]: 'warn',
  [LogLevel.ERROR]: 'error',
};

export function createLogger(module: string): Logger {
  const prefix = `[${module}]`;

  function log(level: LogLevel, msg: string, args: unknown[]): void {
    if (level < currentLevel) return;
    const method = consoleMethods[level] ?? 'log';
    // eslint-disable-next-line no-console
    (console[method] as (...args: unknown[]) => void)(prefix, msg, ...args);
  }

  return {
    debug: (msg: string, ...args: unknown[]) => log(LogLevel.DEBUG, msg, args),
    info: (msg: string, ...args: unknown[]) => log(LogLevel.INFO, msg, args),
    warn: (msg: string, ...args: unknown[]) => log(LogLevel.WARN, msg, args),
    error: (msg: string, ...args: unknown[]) => log(LogLevel.ERROR, msg, args),
  };
}
