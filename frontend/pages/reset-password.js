import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { supabase } from '../lib/supabaseClient';

// Landing page for the link in the password reset email. supabase-js reads the recovery token
// from the URL and signs the user in; this page then lets them set a new password.
export default function ResetPassword() {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // undefined = still reading the link, true = signed in from the link, false = no valid link
  const [ready, setReady] = useState(undefined);
  const router = useRouter();

  useEffect(() => {
    // An expired or already-used link comes back with the error in the URL hash.
    const hash = new URLSearchParams(window.location.hash.slice(1));
    if (hash.get('error')) {
      setReady(false);
      return;
    }

    // The PASSWORD_RECOVERY event can fire before this listener is attached, so the current
    // session is checked as well.
    const { data: listener } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY' || session) setReady(true);
    });
    supabase.auth.getSession().then(({ data: { session } }) => {
      setReady((current) => current || Boolean(session));
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setError('');

    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }

    setSubmitting(true);
    const { error } = await supabase.auth.updateUser({ password });
    setSubmitting(false);

    if (error) {
      const text = error.message && error.message !== '{}' ? error.message : '';
      setError(text || 'Could not update your password. Please try again.');
      return;
    }

    router.push('/dashboard');
  }

  if (ready === undefined) {
    return <p style={{ textAlign: 'center', marginTop: 80 }}>Loading...</p>;
  }

  if (ready === false) {
    return (
      <div className="auth-page">
        <h1>Reset your password</h1>
        <p className="error">This reset link is invalid or has expired.</p>
        <p>
          <Link href="/forgot-password">Send a new reset link</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <h1>Choose a new password</h1>
      <form onSubmit={handleSubmit}>
        <label>
          New password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </label>
        <label>
          Confirm new password
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={6}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Saving…' : 'Save new password'}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
