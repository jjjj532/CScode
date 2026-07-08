import { useState, useEffect } from 'react';
import { X, Trash2, Shield, Plus, GripVertical } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore, type Config, type McpServerConfig, type PluginConfig } from '../../stores/useConfigStore';
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

const KNOWN_PLUGINS = ['code-reviewer', 'test-engineer', 'security-auditor'];

const COMMON_KEYBINDING_ACTIONS = [
  'send_message',
  'new_session',
  'focus_input',
  'cancel',
  'toggle_sidebar',
  'toggle_settings',
];

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
    mcp_servers: [],
    plugins: { enabled: [], settings: {} },
    keybindings: {},
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [customProviderName, setCustomProviderName] = useState('');

  useEffect(() => {
    if (!config) return;
    setForm((prev) => {
      const prevJson = JSON.stringify(prev);
      if (prevJson === JSON.stringify(config)) return prev;
      return {
        ...{ provider: 'openai', model: 'gpt-4o', api_base: null, api_key: '', max_tokens: 4096, temperature: 0.3, top_p: 1, system_prompt: null, mcp_servers: [], plugins: { enabled: [], settings: {} }, keybindings: {} },
        ...config,
      };
    });
    if (config.provider && !['openai', 'anthropic', 'gemini', 'ollama', 'custom'].includes(config.provider)) {
      setCustomProviderName(config.provider);
    }
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
      const payload = { ...form, provider: resolvedProvider, theme };
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

  const updateForm = (partial: Partial<Config>) => setForm((prev) => ({ ...prev, ...partial }));

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={() => setSettingsOpen(false)} />
      <div className="relative w-96 bg-v2-bg-base border-l border-v2-border h-full overflow-y-auto shadow-v2-overlay">
        <div className="flex items-center justify-between p-4 border-b border-v2-border">
          <h2 className="text-sm font-semibold text-v2-text-primary">Settings</h2>
          <button onClick={() => setSettingsOpen(false)} aria-label="Close settings" className="text-v2-text-muted hover:text-v2-text-primary transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Provider */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Provider</label>
            <select
              value={form.provider}
              onChange={(e) => {
                const newProvider = e.target.value;
                const newModels = MODELS[newProvider as keyof typeof MODELS] || MODELS.openai;
                setForm({ ...form, provider: newProvider, model: newModels[0] || '' });
              }}
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

          {/* MCP Servers */}
          <McpServersSection form={form} updateForm={updateForm} />

          {/* Plugins */}
          <PluginsSection form={form} updateForm={updateForm} />

          {/* Keybindings */}
          <KeybindingsSection form={form} updateForm={updateForm} />

          {/* Permission Rules */}
          <PermissionRulesSection />

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving}
            aria-label="Save Settings"
            className="w-full bg-v2-accent text-white py-2 rounded-md text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── MCP Servers ──────────────────────────────────────────────────────────────

function McpServersSection({ form, updateForm }: { form: Config; updateForm: (p: Partial<Config>) => void }) {
  const servers = form.mcp_servers || [];

  const addServer = () => {
    const newServer: McpServerConfig = { name: '', command: '', args: [], env: {}, enabled: true };
    updateForm({ mcp_servers: [...servers, newServer] });
  };

  const removeServer = (idx: number) => {
    updateForm({ mcp_servers: servers.filter((_, i) => i !== idx) });
  };

  const updateServer = (idx: number, field: string, value: unknown) => {
    const updated = servers.map((s, i) => (i === idx ? { ...s, [field]: value } : s));
    updateForm({ mcp_servers: updated });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-medium text-v2-text-secondary">MCP Servers</label>
        <button onClick={addServer} aria-label="Add MCP server" className="text-v2-text-muted hover:text-v2-accent transition-colors" title="Add MCP server">
          <Plus size={14} />
        </button>
      </div>
      {servers.length === 0 ? (
        <p className="text-xs text-v2-text-muted">No MCP servers configured.</p>
      ) : (
        <ul className="space-y-1">
          {servers.map((srv, idx) => (
            <li key={idx} className="bg-v2-bg-deep border border-v2-border rounded-md px-2.5 py-2 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold text-v2-text-muted uppercase tracking-wide">Server {idx + 1}</span>
                <button onClick={() => removeServer(idx)} aria-label="Remove server" className="text-v2-text-muted hover:text-red-400 transition-colors" title="Remove server">
                  <Trash2 size={12} />
                </button>
              </div>
              <input
                type="text"
                value={srv.name}
                onChange={(e) => updateServer(idx, 'name', e.target.value)}
                placeholder="Server name"
                className="w-full bg-v2-bg-base border border-v2-border rounded px-2 py-1 text-xs text-v2-text-primary placeholder-v2-text-muted"
              />
              <input
                type="text"
                value={srv.command}
                onChange={(e) => updateServer(idx, 'command', e.target.value)}
                placeholder="Command (e.g. npx)"
                className="w-full bg-v2-bg-base border border-v2-border rounded px-2 py-1 text-xs text-v2-text-primary placeholder-v2-text-muted"
              />
              <input
                type="text"
                value={srv.args.join(' ')}
                onChange={(e) => updateServer(idx, 'args', e.target.value.split(/\s+/).filter(Boolean))}
                placeholder="Arguments (space-separated)"
                className="w-full bg-v2-bg-base border border-v2-border rounded px-2 py-1 text-xs text-v2-text-primary placeholder-v2-text-muted"
              />
              <label className="flex items-center gap-2 text-xs text-v2-text-secondary">
                <input
                  type="checkbox"
                  checked={srv.enabled}
                  onChange={(e) => updateServer(idx, 'enabled', e.target.checked)}
                  className="accent-v2-accent"
                />
                Enabled
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Plugins ──────────────────────────────────────────────────────────────────

function PluginsSection({ form, updateForm }: { form: Config; updateForm: (p: Partial<Config>) => void }) {
  const pluginCfg: PluginConfig = form.plugins || { enabled: [], settings: {} };
  const enabledSet = new Set(pluginCfg.enabled);

  const togglePlugin = (name: string) => {
    const next = enabledSet.has(name)
      ? pluginCfg.enabled.filter((p) => p !== name)
      : [...pluginCfg.enabled, name];
    updateForm({ plugins: { ...pluginCfg, enabled: next } });
  };

  return (
    <div>
      <label className="block text-xs font-medium text-v2-text-secondary mb-1">Plugins</label>
      {KNOWN_PLUGINS.length === 0 ? (
        <p className="text-xs text-v2-text-muted">No plugins available.</p>
      ) : (
        <ul className="space-y-1">
          {KNOWN_PLUGINS.map((name) => (
            <li key={name} className="flex items-center justify-between bg-v2-bg-deep border border-v2-border rounded-md px-2.5 py-1.5">
              <span className="text-xs text-v2-text-primary">{name}</span>
              <label className="flex items-center gap-1.5 text-xs text-v2-text-secondary">
                <input
                  type="checkbox"
                  checked={enabledSet.has(name)}
                  onChange={() => togglePlugin(name)}
                  className="accent-v2-accent"
                />
                Enable
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Keybindings ──────────────────────────────────────────────────────────────

function KeybindingsSection({ form, updateForm }: { form: Config; updateForm: (p: Partial<Config>) => void }) {
  const kb: Record<string, string> = form.keybindings || {};
  const [newAction, setNewAction] = useState('');
  const [newKey, setNewKey] = useState('');

  const updateKeybinding = (action: string, value: string) => {
    updateForm({ keybindings: { ...kb, [action]: value } });
  };

  const removeKeybinding = (action: string) => {
    const next = { ...kb };
    delete next[action];
    updateForm({ keybindings: next });
  };

  const addKeybinding = () => {
    if (!newAction.trim() || !newKey.trim()) return;
    updateForm({ keybindings: { ...kb, [newAction.trim()]: newKey.trim() } });
    setNewAction('');
    setNewKey('');
  };

  const allActions = [...new Set([...COMMON_KEYBINDING_ACTIONS, ...Object.keys(kb)])];

  return (
    <div>
      <label className="block text-xs font-medium text-v2-text-secondary mb-1">Keybindings</label>
      <ul className="space-y-1">
        {allActions.map((action) => (
          <li key={action} className="flex items-center gap-2 bg-v2-bg-deep border border-v2-border rounded-md px-2.5 py-1.5">
            <span className="text-[10px] font-mono text-v2-text-muted w-28 shrink-0 truncate">{action}</span>
            <input
              type="text"
              value={kb[action] || ''}
              onChange={(e) => updateKeybinding(action, e.target.value)}
              placeholder="e.g. Enter"
              className="flex-1 bg-v2-bg-base border border-v2-border rounded px-1.5 py-0.5 text-xs text-v2-text-primary placeholder-v2-text-muted min-w-0"
            />
            <button onClick={() => removeKeybinding(action)} aria-label="Remove keybinding" className="text-v2-text-muted hover:text-red-400 transition-colors shrink-0" title="Remove keybinding">
              <Trash2 size={12} />
            </button>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2 mt-1.5">
        <input
          type="text"
          value={newAction}
          onChange={(e) => setNewAction(e.target.value)}
          placeholder="Action name"
          className="flex-1 bg-v2-bg-deep border border-v2-border rounded px-2 py-1 text-xs text-v2-text-primary placeholder-v2-text-muted min-w-0"
        />
        <input
          type="text"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder="Shortcut"
          className="w-20 bg-v2-bg-deep border border-v2-border rounded px-2 py-1 text-xs text-v2-text-primary placeholder-v2-text-muted"
        />
        <button onClick={addKeybinding} aria-label="Add keybinding" className="text-v2-text-muted hover:text-v2-accent transition-colors shrink-0" title="Add keybinding">
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
}

// ─── Permission Rules ─────────────────────────────────────────────────────────

interface PermissionRule {
  id: string;
  pattern: string;
  allow: boolean;
  label: string;
}

function PermissionRulesSection() {
  const [rules, setRules] = useState<PermissionRule[]>([]);
  const [loading, setLoading] = useState(true);
  const addToast = useToastStore((s) => s.addToast);

  useEffect(() => {
    api.permissionRules.list()
      .then(setRules)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async (id: string) => {
    try {
      await api.permissionRules.delete(id);
      setRules((prev) => prev.filter((r) => r.id !== id));
    } catch {
      addToast('Failed to delete rule', 'error');
    }
  };

  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-v2-text-secondary mb-1">
        <Shield size={12} />
        Permission Rules
      </label>
      {loading ? (
        <p className="text-xs text-v2-text-muted">Loading...</p>
      ) : rules.length === 0 ? (
        <p className="text-xs text-v2-text-muted">No saved permission rules.</p>
      ) : (
        <ul className="space-y-1">
          {rules.map((rule) => (
            <li key={rule.id} className="flex items-center justify-between bg-v2-bg-deep border border-v2-border rounded-md px-2.5 py-1.5">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-mono text-v2-text-primary truncate">{rule.pattern}</p>
                <p className="text-[10px] text-v2-text-muted">
                  {rule.allow ? 'Allowed' : 'Denied'}
                  {rule.label ? ` · ${rule.label}` : ''}
                </p>
              </div>
              <button
                onClick={() => handleDelete(rule.id)}
                aria-label="Delete rule"
                className="ml-2 text-v2-text-muted hover:text-red-400 transition-colors shrink-0"
                title="Delete rule"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
