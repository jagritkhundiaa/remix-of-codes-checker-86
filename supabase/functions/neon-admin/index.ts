import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

function getSupabase() {
  return createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  );
}

function generateKey(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  const seg = (n: number) => Array.from({ length: n }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
  return `NEON-${seg(4)}-${seg(4)}`;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });

  try {
    const { action, adminKey, ...params } = await req.json();

    if (!adminKey) {
      return new Response(JSON.stringify({ error: 'Missing admin key' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabase = getSupabase();

    // Validate admin key
    const { data: keyData } = await supabase
      .from('access_keys')
      .select('*')
      .eq('key', adminKey)
      .eq('is_active', true)
      .eq('is_admin', true)
      .single();

    if (!keyData) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 403, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    let result: unknown;

    switch (action) {
      // ============= KEY MANAGEMENT =============
      case 'generate_key': {
        const key = generateKey();
        const { data, error } = await supabase.from('access_keys').insert({
          key,
          label: params.label || null,
          is_admin: params.isAdmin || false,
          expires_at: params.expiresAt || null,
        }).select().single();
        if (error) throw error;
        result = data;
        break;
      }

      case 'list_keys': {
        const { data, error } = await supabase
          .from('access_keys')
          .select('*')
          .order('created_at', { ascending: false });
        if (error) throw error;
        result = data;
        break;
      }

      case 'toggle_key': {
        const { data, error } = await supabase
          .from('access_keys')
          .update({ is_active: params.isActive })
          .eq('id', params.keyId)
          .select()
          .single();
        if (error) throw error;
        result = data;
        break;
      }

      case 'delete_key': {
        const { error } = await supabase
          .from('access_keys')
          .delete()
          .eq('id', params.keyId)
          .neq('key', 'NEONISTHEGOAT'); // Protect master key
        if (error) throw error;
        result = { deleted: true };
        break;
      }

      // ============= LOGS =============
      case 'get_logs': {
        const limit = params.limit || 100;
        const offset = params.offset || 0;
        let query = supabase
          .from('check_logs')
          .select('*', { count: 'exact' })
          .order('created_at', { ascending: false })
          .range(offset, offset + limit - 1);

        if (params.status) query = query.eq('status', params.status);
        if (params.accessKey) query = query.eq('access_key', params.accessKey);

        const { data, error, count } = await query;
        if (error) throw error;
        result = { logs: data, total: count };
        break;
      }

      case 'get_stats': {
        const { data: logs } = await supabase.from('check_logs').select('status, mode');
        const stats = {
          totalChecks: logs?.length || 0,
          hits: logs?.filter(l => ['live', 'charged', '3ds'].includes(l.status)).length || 0,
          declines: logs?.filter(l => l.status === 'declined').length || 0,
          errors: logs?.filter(l => l.status === 'error').length || 0,
          hitterChecks: logs?.filter(l => l.mode === 'hitter').length || 0,
          bypasserChecks: logs?.filter(l => l.mode === 'bypasser').length || 0,
        };
        
        const { data: keys } = await supabase.from('access_keys').select('*');
        const { data: proxies } = await supabase.from('proxies').select('*');
        
        result = {
          ...stats,
          totalKeys: keys?.length || 0,
          activeKeys: keys?.filter(k => k.is_active).length || 0,
          totalProxies: proxies?.length || 0,
          activeProxies: proxies?.filter(p => p.is_active).length || 0,
        };
        break;
      }

      // ============= PROXY MANAGEMENT =============
      case 'add_proxies': {
        const lines = (params.proxies as string).split('\n').filter((l: string) => l.trim());
        const rows = lines.map((line: string) => {
          const trimmed = line.trim();
          let protocol = 'http';
          let proxy = trimmed;
          if (trimmed.startsWith('socks5://')) { protocol = 'socks5'; proxy = trimmed.slice(9); }
          else if (trimmed.startsWith('socks4://')) { protocol = 'socks4'; proxy = trimmed.slice(9); }
          else if (trimmed.startsWith('https://')) { protocol = 'https'; proxy = trimmed.slice(8); }
          else if (trimmed.startsWith('http://')) { protocol = 'http'; proxy = trimmed.slice(7); }
          return { proxy, protocol, is_active: true };
        });

        const { data, error } = await supabase.from('proxies').insert(rows).select();
        if (error) throw error;
        result = { added: data?.length || 0 };
        break;
      }

      case 'list_proxies': {
        const { data, error } = await supabase
          .from('proxies')
          .select('*')
          .order('created_at', { ascending: false });
        if (error) throw error;
        result = data;
        break;
      }

      case 'toggle_proxy': {
        const { data, error } = await supabase
          .from('proxies')
          .update({ is_active: params.isActive })
          .eq('id', params.proxyId)
          .select()
          .single();
        if (error) throw error;
        result = data;
        break;
      }

      case 'delete_proxy': {
        const { error } = await supabase
          .from('proxies')
          .delete()
          .eq('id', params.proxyId);
        if (error) throw error;
        result = { deleted: true };
        break;
      }

      case 'delete_all_proxies': {
        const { error } = await supabase.from('proxies').delete().neq('id', '00000000-0000-0000-0000-000000000000');
        if (error) throw error;
        result = { deleted: true };
        break;
      }

      case 'check_proxy': {
        const proxy = params.proxy as string;
        const start = Date.now();
        try {
          const resp = await fetch('https://httpbin.org/ip', { signal: AbortSignal.timeout(10000) });
          const elapsed = Date.now() - start;
          if (resp.ok) {
            await supabase.from('proxies').update({
              last_checked: new Date().toISOString(),
              last_status: `OK (${elapsed}ms)`,
              success_count: (params.currentSuccess || 0) + 1,
            }).eq('id', params.proxyId);
            result = { status: 'ok', time: elapsed };
          } else {
            await supabase.from('proxies').update({
              last_checked: new Date().toISOString(),
              last_status: `FAIL (HTTP ${resp.status})`,
              fail_count: (params.currentFail || 0) + 1,
            }).eq('id', params.proxyId);
            result = { status: 'fail', error: `HTTP ${resp.status}` };
          }
        } catch (e) {
          const msg = e instanceof Error ? e.message : 'Unknown';
          await supabase.from('proxies').update({
            last_checked: new Date().toISOString(),
            last_status: `FAIL (${msg})`,
            fail_count: (params.currentFail || 0) + 1,
          }).eq('id', params.proxyId);
          result = { status: 'fail', error: msg };
        }
        break;
      }

      default:
        return new Response(JSON.stringify({ error: `Unknown action: ${action}` }), {
          status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
    }

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });

  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : 'Unknown error';
    return new Response(JSON.stringify({ error: msg }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
