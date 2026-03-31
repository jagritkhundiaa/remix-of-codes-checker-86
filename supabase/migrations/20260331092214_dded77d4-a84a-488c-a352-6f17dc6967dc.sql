
-- Check logs table for activity tracking
CREATE TABLE public.check_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  access_key text NOT NULL,
  card_masked text NOT NULL,
  bin text,
  brand text,
  status text NOT NULL,
  code text,
  message text,
  merchant text,
  amount text,
  response_time real,
  mode text DEFAULT 'hitter',
  provider text
);

ALTER TABLE public.check_logs ENABLE ROW LEVEL SECURITY;

-- Proxies table
CREATE TABLE public.proxies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  proxy text NOT NULL,
  protocol text NOT NULL DEFAULT 'http',
  is_active boolean NOT NULL DEFAULT true,
  last_checked timestamptz,
  last_status text,
  success_count integer NOT NULL DEFAULT 0,
  fail_count integer NOT NULL DEFAULT 0
);

ALTER TABLE public.proxies ENABLE ROW LEVEL SECURITY;

-- Add label and is_admin to access_keys
ALTER TABLE public.access_keys ADD COLUMN IF NOT EXISTS label text;
ALTER TABLE public.access_keys ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;
ALTER TABLE public.access_keys ADD COLUMN IF NOT EXISTS usage_count integer NOT NULL DEFAULT 0;

-- Insert master admin key
INSERT INTO public.access_keys (key, label, is_admin) VALUES ('NEONISTHEGOAT', 'Master Admin', true)
ON CONFLICT (key) DO UPDATE SET is_admin = true, label = 'Master Admin';
