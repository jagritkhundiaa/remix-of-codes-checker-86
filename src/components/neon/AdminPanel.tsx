import { useState, useEffect } from "react";
import { KeyRound, Users, Activity, Wifi, Plus, Trash2, Power, RefreshCw, BarChart3, Copy, Check, X } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { AccessKeyData, ProxyData, LogEntry } from "@/lib/neon";

interface AdminPanelProps {
  adminKey: string;
  onClose: () => void;
}

type Tab = 'overview' | 'keys' | 'proxies' | 'logs';

export default function AdminPanel({ adminKey, onClose }: AdminPanelProps) {
  const [tab, setTab] = useState<Tab>('overview');
  const [stats, setStats] = useState<Record<string, number>>({});
  const [keys, setKeys] = useState<AccessKeyData[]>([]);
  const [proxies, setProxies] = useState<ProxyData[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logsTotal, setLogsTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  // Key gen
  const [newLabel, setNewLabel] = useState("");
  const [newAdmin, setNewAdmin] = useState(false);
  const [newExpiry, setNewExpiry] = useState("");

  // Proxy add
  const [proxyText, setProxyText] = useState("");

  // Copied
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const api = async (action: string, params: Record<string, unknown> = {}) => {
    const { data } = await supabase.functions.invoke("neon-admin", {
      body: { action, adminKey, ...params },
    });
    return data;
  };

  useEffect(() => {
    loadTab(tab);
  }, [tab]);

  const loadTab = async (t: Tab) => {
    setLoading(true);
    try {
      if (t === 'overview') {
        const s = await api('get_stats');
        if (s && !s.error) setStats(s);
      } else if (t === 'keys') {
        const k = await api('list_keys');
        if (Array.isArray(k)) setKeys(k as AccessKeyData[]);
      } else if (t === 'proxies') {
        const p = await api('list_proxies');
        if (Array.isArray(p)) setProxies(p as ProxyData[]);
      } else if (t === 'logs') {
        const l = await api('get_logs', { limit: 200 });
        if (l?.logs) { setLogs(l.logs as LogEntry[]); setLogsTotal(l.total || 0); }
      }
    } catch {}
    setLoading(false);
  };

  const handleGenKey = async () => {
    const res = await api('generate_key', {
      label: newLabel || null,
      isAdmin: newAdmin,
      expiresAt: newExpiry || null,
    });
    if (res && !res.error) {
      setNewLabel(""); setNewAdmin(false); setNewExpiry("");
      loadTab('keys');
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleToggleKey = async (id: string, active: boolean) => {
    await api('toggle_key', { keyId: id, isActive: !active });
    loadTab('keys');
  };

  const handleDeleteKey = async (id: string) => {
    await api('delete_key', { keyId: id });
    loadTab('keys');
  };

  const handleAddProxies = async () => {
    if (!proxyText.trim()) return;
    await api('add_proxies', { proxies: proxyText });
    setProxyText("");
    loadTab('proxies');
  };

  const handleDeleteProxy = async (id: string) => {
    await api('delete_proxy', { proxyId: id });
    loadTab('proxies');
  };

  const handleDeleteAllProxies = async () => {
    await api('delete_all_proxies');
    loadTab('proxies');
  };

  const handleToggleProxy = async (id: string, active: boolean) => {
    await api('toggle_proxy', { proxyId: id, isActive: !active });
    loadTab('proxies');
  };

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'Overview', icon: <BarChart3 className="w-3 h-3" /> },
    { key: 'keys', label: 'Keys', icon: <KeyRound className="w-3 h-3" /> },
    { key: 'proxies', label: 'Proxies', icon: <Wifi className="w-3 h-3" /> },
    { key: 'logs', label: 'Logs', icon: <Activity className="w-3 h-3" /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
      <div className="w-full max-w-4xl max-h-[90vh] glass-strong rounded-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border/30">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" />
            <span className="text-sm font-bold text-primary uppercase tracking-wider">Admin Panel</span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-sm">✕</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border/20 px-4">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
                tab === t.key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
          <button onClick={() => loadTab(tab)} className="ml-auto text-muted-foreground hover:text-primary transition-colors p-2">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {tab === 'overview' && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Total Checks" value={stats.totalChecks || 0} />
              <StatCard label="Hits" value={stats.hits || 0} color="text-primary" />
              <StatCard label="Declines" value={stats.declines || 0} color="text-destructive" />
              <StatCard label="Errors" value={stats.errors || 0} color="text-muted-foreground" />
              <StatCard label="Hitter Checks" value={stats.hitterChecks || 0} />
              <StatCard label="Bypasser Checks" value={stats.bypasserChecks || 0} />
              <StatCard label="Active Keys" value={`${stats.activeKeys || 0}/${stats.totalKeys || 0}`} />
              <StatCard label="Active Proxies" value={`${stats.activeProxies || 0}/${stats.totalProxies || 0}`} />
            </div>
          )}

          {tab === 'keys' && (
            <div className="space-y-4">
              {/* Generate new key */}
              <div className="bg-background/40 rounded-xl p-4 border border-border/20">
                <h3 className="text-xs font-bold uppercase tracking-wider text-primary mb-3">Generate New Key</h3>
                <div className="flex flex-wrap gap-2">
                  <input
                    type="text"
                    value={newLabel}
                    onChange={(e) => setNewLabel(e.target.value)}
                    placeholder="Label (optional)"
                    className="flex-1 min-w-[150px] h-9 px-3 rounded-lg bg-background/50 border border-border/40 text-foreground text-xs font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/50"
                  />
                  <input
                    type="datetime-local"
                    value={newExpiry}
                    onChange={(e) => setNewExpiry(e.target.value)}
                    className="h-9 px-3 rounded-lg bg-background/50 border border-border/40 text-foreground text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                  />
                  <label className="flex items-center gap-1 text-xs text-muted-foreground">
                    <input type="checkbox" checked={newAdmin} onChange={(e) => setNewAdmin(e.target.checked)} className="rounded" />
                    Admin
                  </label>
                  <button onClick={handleGenKey} className="h-9 px-4 rounded-lg bg-primary text-primary-foreground font-bold text-xs flex items-center gap-1 hover:opacity-90">
                    <Plus className="w-3 h-3" /> Generate
                  </button>
                </div>
              </div>

              {/* Keys list */}
              <div className="space-y-2">
                {keys.map(k => (
                  <div key={k.id} className={`flex items-center gap-3 p-3 rounded-xl border ${k.is_active ? 'bg-background/30 border-border/20' : 'bg-destructive/5 border-destructive/20 opacity-60'}`}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-xs font-mono text-foreground">{k.key}</code>
                        <button onClick={() => handleCopy(k.key, k.id)} className="text-muted-foreground hover:text-primary">
                          {copiedId === k.id ? <Check className="w-3 h-3 text-primary" /> : <Copy className="w-3 h-3" />}
                        </button>
                        {k.is_admin && <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/20 text-accent-foreground font-bold">ADMIN</span>}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {k.label || 'No label'} · {k.usage_count} uses · Created {new Date(k.created_at).toLocaleDateString()}
                        {k.expires_at && ` · Expires ${new Date(k.expires_at).toLocaleDateString()}`}
                      </div>
                    </div>
                    <button onClick={() => handleToggleKey(k.id, k.is_active)} className="text-muted-foreground hover:text-foreground">
                      <Power className={`w-3 h-3 ${k.is_active ? 'text-primary' : 'text-destructive'}`} />
                    </button>
                    {k.key !== 'NEONISTHEGOAT' && (
                      <button onClick={() => handleDeleteKey(k.id)} className="text-muted-foreground hover:text-destructive">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'proxies' && (
            <div className="space-y-4">
              {/* Add proxies */}
              <div className="bg-background/40 rounded-xl p-4 border border-border/20">
                <h3 className="text-xs font-bold uppercase tracking-wider text-primary mb-3">Add Proxies</h3>
                <textarea
                  value={proxyText}
                  onChange={(e) => setProxyText(e.target.value)}
                  placeholder={"ip:port\nuser:pass@ip:port\nsocks5://ip:port\nhttp://user:pass@ip:port"}
                  rows={4}
                  className="w-full px-3 py-2 rounded-lg bg-background/50 border border-border/40 text-foreground text-xs font-mono placeholder:text-muted-foreground/30 focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none mb-2"
                />
                <div className="flex gap-2">
                  <button onClick={handleAddProxies} disabled={!proxyText.trim()} className="h-9 px-4 rounded-lg bg-primary text-primary-foreground font-bold text-xs flex items-center gap-1 hover:opacity-90 disabled:opacity-40">
                    <Plus className="w-3 h-3" /> Add
                  </button>
                  {proxies.length > 0 && (
                    <button onClick={handleDeleteAllProxies} className="h-9 px-4 rounded-lg bg-destructive/20 text-destructive font-bold text-xs flex items-center gap-1 hover:bg-destructive/30">
                      <Trash2 className="w-3 h-3" /> Clear All
                    </button>
                  )}
                </div>
              </div>

              {/* Proxy list */}
              <div className="space-y-1">
                {proxies.length === 0 && <p className="text-xs text-muted-foreground/50 text-center py-4">No proxies added</p>}
                {proxies.map(p => (
                  <div key={p.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-xs ${p.is_active ? 'bg-background/30 border-border/20' : 'bg-destructive/5 border-destructive/20 opacity-60'}`}>
                    <span className={`w-2 h-2 rounded-full ${p.is_active ? 'bg-primary' : 'bg-destructive'}`} />
                    <code className="font-mono text-muted-foreground flex-1 truncate">{p.protocol}://{p.proxy}</code>
                    <span className="text-[10px] text-muted-foreground/50">{p.success_count}✓ {p.fail_count}✗</span>
                    {p.last_status && <span className="text-[10px] text-muted-foreground/40 truncate max-w-[100px]">{p.last_status}</span>}
                    <button onClick={() => handleToggleProxy(p.id, p.is_active)} className="text-muted-foreground hover:text-foreground">
                      <Power className={`w-3 h-3 ${p.is_active ? 'text-primary' : 'text-destructive'}`} />
                    </button>
                    <button onClick={() => handleDeleteProxy(p.id)} className="text-muted-foreground hover:text-destructive">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === 'logs' && (
            <div>
              <div className="text-xs text-muted-foreground mb-3">Showing {logs.length} of {logsTotal} logs</div>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="text-muted-foreground/60 uppercase tracking-widest border-b border-border/20">
                      <th className="text-left py-2 px-2">Time</th>
                      <th className="text-left py-2 px-2">Card</th>
                      <th className="text-left py-2 px-2">Status</th>
                      <th className="text-left py-2 px-2">Code</th>
                      <th className="text-left py-2 px-2">Mode</th>
                      <th className="text-left py-2 px-2">Merchant</th>
                      <th className="text-left py-2 px-2">Key</th>
                      <th className="text-right py-2 px-2">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map(l => (
                      <tr key={l.id} className="border-b border-border/10 hover:bg-background/30">
                        <td className="py-1.5 px-2 text-muted-foreground/50">{new Date(l.created_at).toLocaleString()}</td>
                        <td className="py-1.5 px-2 font-mono text-muted-foreground">{l.card_masked}</td>
                        <td className={`py-1.5 px-2 font-bold uppercase ${
                          ['live','charged','3ds'].includes(l.status) ? 'text-primary' : l.status === 'declined' ? 'text-destructive' : 'text-muted-foreground'
                        }`}>{l.status}</td>
                        <td className="py-1.5 px-2 text-muted-foreground/60">{l.code}</td>
                        <td className="py-1.5 px-2">
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${l.mode === 'bypasser' ? 'bg-accent/20 text-accent-foreground' : 'bg-primary/10 text-primary'}`}>
                            {l.mode?.toUpperCase() || 'HITTER'}
                          </span>
                        </td>
                        <td className="py-1.5 px-2 text-muted-foreground/60 truncate max-w-[120px]">{l.merchant}</td>
                        <td className="py-1.5 px-2 font-mono text-muted-foreground/40 truncate max-w-[80px]">{l.access_key?.slice(0, 12)}</td>
                        <td className="py-1.5 px-2 text-right text-muted-foreground/40">{l.response_time?.toFixed(1)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {logs.length === 0 && <p className="text-xs text-muted-foreground/50 text-center py-8">No logs yet</p>}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-background/40 rounded-xl px-4 py-3 border border-border/20">
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className={`text-2xl font-black ${color || 'text-foreground'}`}>{value}</div>
    </div>
  );
}
