import { useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { supabase } from '../lib/supabaseClient';

export default function SignUp() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const router = useRouter();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setMessage('');

    const { data, error } = await supabase.auth.signUp({ email, password });

    if (error) {
      setError(error.message);
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
        <button type="submit">Sign up</button>
      </form>
      {message && <p className="info">{message}</p>}
      {error && <p className="error">{error}</p>}
      <p>
        Already have an account? <Link href="/signin">Sign in</Link>
      </p>
    </div>
  );
}
