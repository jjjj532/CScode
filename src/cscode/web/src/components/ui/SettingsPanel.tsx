import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore, type Config } from '../../stores/useConfigStore';
import { useToastStore } from '../../stores/useToastStore';
import { themes } from '../../themes';
import { api } from '../../lib/api';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'custom', label: 'Custom' },
];

const MODELS: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1-mini', 'o3-mini'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3.5-sonnet', 'claude-3-opus'],
  gemini: ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro'],
  ollama: ['llama3', 'mistral', 'codellama', 'qwen2.5-coder', 'deepseek-coder'],
};

export function SettingsPanel() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);

  const config = useConfigStore((s) => s.config);
  const setConfig = useConfigStore((s) => s.setConfig);
  const addToast = useToastStore((s) => s.addToast);

  const [form, setForm] = useState<Config>({
    provider: 'openai',
    model: 'gpt-4o',
    api_base: null,
    api_key: '',
    max_tokens: 4096,
    temperature: 0.3,
    top_p: 1,
    system_prompt: null,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [customProviderName, setCustomProviderName] = useState('');

  useEffect(() => {
    if (config) {
      // Only update if config is different from current form
      const configJson = JSON.stringify(config);
      const formJson = JSON.stringify(form);
      if (configJson !== formJson) {
        setForm(config);
        if (config.provider && !['openai', 'anthropic', 'gemini', 'ollama', 'custom'].includes(config.provider)) {
          setCustomProviderName(config.provider);
          setForm((prev) => ({ ...prev, provider: 'custom' }));
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const resolvedProvider = form.provider === 'custom' ? (customProviderName || 'custom') : form.provider;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSettingsOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [setSettingsOpen]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...form, provider: resolvedProvider };
      await api.config.save(payload);
      setConfig(payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      addToast('Failed to save settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const models = MODELS[form.provider as keyof typeof MODELS] || MODELS.openai;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={() => setSettingsOpen(false)} />
      <div className="relative w-96 bg-v2-bg-base border-l border-v2-border h-full overflow-y-auto shadow-v2-overlay">
        <div className="flex items-center justify-between p-4 border-b border-v2-border">
          <h2 className="text-sm font-semibold text-v2-text-primary">Settings</h2>
          <button onClick={() => setSettingsOpen(false)} className="text-v2-text-muted hover:text-v2-text-primary transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Provider */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Provider</label>
            <select
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value, model: '' })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {form.provider === 'custom' && (
            <div>
              <label className="block text-xs font-medium text-v2-text-secondary mb-1">Custom Provider Name</label>
              <input
                type="text"
                value={customProviderName}
                onChange={(e) => setCustomProviderName(e.target.value)}
                placeholder="e.g. my-provider"
                className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary placeholder-v2-text-muted"
              />
            </div>
          )}

          {/* Model */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Model</label>
            {form.provider === 'custom' ? (
              <input
                type="text"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                placeholder="Enter model name"
                className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary placeholder-v2-text-muted"
              />
            ) : (
              <select
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
              >
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </div>

          {/* API Base URL */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">API Base URL</label>
            <input
              type="text"
              value={form.api_base || ''}
              onChange={(e) => setForm({ ...form, api_base: e.target.value || null })}
              placeholder="https://api.openai.com"
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary placeholder-v2-text-muted"
            />
          </div>

          {/* API Key */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">API Key</label>
            <input
              type="password"
              value={form.api_key || ''}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            />
          </div>

          {/* Temperature */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">
              Temperature ({form.temperature})
            </label>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={form.temperature}
              onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) })}
              className="w-full accent-v2-accent"
            />
          </div>

          {/* Max Tokens */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Max Tokens</label>
            <input
              type="number"
              value={form.max_tokens}
              onChange={(e) => setForm({ ...form, max_tokens: parseInt(e.target.value) || 4096 })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            />
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">System Prompt</label>
            <textarea
              value={form.system_prompt || ''}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value || null })}
              rows={4}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary resize-none"
            />
          </div>

          {/* Theme */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Theme</label>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as typeof theme)}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            >
              {themes.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full bg-v2-accent text-white py-2 rounded-md text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
