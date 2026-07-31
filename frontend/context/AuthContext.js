import { createContext, useContext, useEffect, useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const AuthContext = createContext({ user: null, loading: true, isAdmin: false });

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!user) {
      setIsAdmin(false);
      return;
    }

    let cancelled = false;

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      // 403 for a non-admin is the expected, common case here, not an error - the
      // ADMIN_EMAILS allowlist only lives in the backend, so this is the only way the
      // frontend can know whether to show the Admin nav link at all.
      fetch(`${API_URL}/api/admin/me`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
        .then((res) => {
          if (!cancelled) setIsAdmin(res.ok);
        })
        .catch(() => {
          if (!cancelled) setIsAdmin(false);
        });
    });

    return () => {
      cancelled = true;
    };
  }, [user]);

  return (
    <AuthContext.Provider value={{ user, loading, isAdmin }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
