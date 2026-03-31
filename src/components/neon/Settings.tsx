import { Settings as SettingsIcon, Zap, Shield, Bell, Timer } from "lucide-react";
import { NeonSettings, loadSettings, saveSettings } from "@/lib/neon";
import { useState, useEffect } from "react";

interface SettingsProps {
  settings: NeonSettings;
  onSettingsChange: (s: NeonSettings) => void;
}

export default function Settings({ settings, onSettingsChange }: SettingsProps) {
  const [open, setOpen] = useState(false);

  const toggle = (key: keyof NeonSettings) => {
    const updated = { ...settings, [key]: !settings[key] };
    onSettingsChange(updated);
    saveSettings(updated);
  };

  const setDelay = (val: number) => {
    const updated = { ...settings, delayMs: val };
    onSettingsChange(updated);
    saveSettings(updated);
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-20 right-4 z-50 w-10 h-10 rounded-full glass flex items-center justify-center hover:bg-primary/20 transition-all"
      >
        <SettingsIcon className="w-4 h-4 text-primary" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-20 right-4 z-50 w-72 glass rounded-2xl p-4 shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <SettingsIcon className="w-4 h-4 text-primary" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-primary">Settings</h3>
        </div>
        <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground text-xs">✕</button>
      </div>

      <div className="space-y-3">
        <ToggleRow icon={<Zap className="w-3 h-3" />} label="Hitter Mode" active={settings.hitterEnabled} onToggle={() => toggle('hitterEnabled')} />
        <ToggleRow icon={<Shield className="w-3 h-3" />} label="Bypasser Mode" active={settings.bypasserEnabled} onToggle={() => toggle('bypasserEnabled')} />
        <ToggleRow icon={<Bell className="w-3 h-3" />} label="Telegram Logs" active={settings.autoTelegram} onToggle={() => toggle('autoTelegram')} />

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Timer className="w-3 h-3" />
            Delay (ms)
          </div>
          <input
            type="number"
            min={200}
            max={5000}
            step={100}
            value={settings.delayMs}
            onChange={(e) => setDelay(Math.max(200, Math.min(5000, parseInt(e.target.value) || 800)))}
            className="w-20 h-7 px-2 rounded-lg bg-background/50 border border-border/40 text-foreground text-xs font-mono text-center focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>
      </div>

      <p className="text-[9px] text-muted-foreground/40 mt-3">Settings auto-save</p>
    </div>
  );
}

function ToggleRow({ icon, label, active, onToggle }: { icon: React.ReactNode; label: string; active: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <button
        onClick={onToggle}
        className={`w-10 h-5 rounded-full relative transition-colors ${active ? 'bg-primary' : 'bg-muted'}`}
      >
        <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-foreground transition-transform ${active ? 'left-5' : 'left-0.5'}`} />
      </button>
    </div>
  );
}
