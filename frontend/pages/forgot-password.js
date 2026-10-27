import { useState } from 'react';
import Link from 'next/link';
import { supabase } from '../lib/supabaseClient';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError('');
    setMessage('');

    // The reset link signs the user in and lands on /reset-password, where they choose a new
    // password. Supabase only honours redirectTo if the URL is in the project's Redirect URLs.
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    setSubmitting(false);

    if (error) {
      // Some auth errors arrive with an empty body, which supabase-js surfaces as the message "{}".
      const text = error.message && error.message !== '{}' ? error.message : '';
      setError(text || 'Could not send the reset email. Please try again in a moment.');
      return;
    }

    // Same message whether or not the email has an account, so the form can't be used to
    // find out who has signed up.
    setMessage('If an account exists for that email, a password reset link is on its way.');
  }

  return (
    <div className="auth-page">
      <h1>Reset your password</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
      {message && <p className="info">{message}</p>}
      {error && <p className="error">{error}</p>}
      <p>
        Remembered it? <Link href="/signin">Sign in</Link>
      </p>
    </div>
  );
}
