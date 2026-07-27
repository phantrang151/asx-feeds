import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  // Fails loudly at import time rather than silently returning an unusable client -
  // easier to debug than a confusing runtime error deep in a component.
  console.warn(
    'NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set - copy .env.local.example to .env.local and fill them in.'
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
