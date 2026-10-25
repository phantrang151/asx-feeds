import { useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { supabase } from '../lib/supabaseClient';

export default function SignUp() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError('');
    setMessage('');

    // emailRedirectTo sends the confirmation link back to whichever site the user signed up on;
    // Supabase only honours it if the URL is in the project's Redirect URLs allow-list.
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/dashboard` },
    });
    setSubmitting(false);

    if (error) {
      // Some auth errors arrive with an empty body, which supabase-js surfaces as the message "{}".
      const text = error.message && error.message !== '{}' ? error.message : '';
      setError(text || 'Sign up failed. Please try again in a moment.');
      return;
    }

    if (data.session) {
      // Email confirmation is off - the session is active immediately.
      router.push('/dashboard');
    } else {
      // Email confirmation is on - Supabase sent a confirmation link.
      setMessage('Check your email to confirm your account, then sign in.');
    }
  }

  return (
    <div className="auth-page">
      <h1>Sign up</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Signing up…' : 'Sign up'}
        </button>
      </form>
      {message && <p className="info">{message}</p>}
      {error && <p className="error">{error}</p>}
      <p>
        Already have an account? <Link href="/signin">Sign in</Link>
      </p>
    </div>
  );
}
