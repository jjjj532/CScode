import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'v2-bg-deep': 'var(--bg-deep)',
        'v2-bg-base': 'var(--bg-base)',
        'v2-bg-surface': 'var(--bg-surface)',
        'v2-text-primary': 'var(--text-primary)',
        'v2-text-secondary': 'var(--text-secondary)',
        'v2-text-muted': 'var(--text-muted)',
        'v2-accent': 'var(--accent-primary)',
        'v2-accent-secondary': 'var(--accent-secondary)',
        'v2-border': 'var(--border)',
        'v2-border-light': 'var(--border-light)',
        'v2-msg-user': 'var(--msg-user-bg)',
        'v2-msg-assistant': 'var(--msg-assistant-bg)',
        'v2-code-bg': 'var(--code-bg)',
        'v2-code-header': 'var(--code-header)',
      },
      boxShadow: {
        'v2-raised': 'var(--elevation-raised)',
        'v2-overlay': 'var(--elevation-overlay)',
      },
      borderRadius: {
        'v2': '10px',
      },
    },
  },
  plugins: [],
};

export default config;
