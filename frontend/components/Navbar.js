import Link from 'next/link';
import { useRouter } from 'next/router';
import { supabase } from '../lib/supabaseClient';
import { useAuth } from '../context/AuthContext';

export default function Navbar() {
  const { user, isAdmin } = useAuth();
  const router = useRouter();

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.push('/signin');
  }

  return (
    <nav className="navbar">
      <div className="nav-links">
        <Link href="/dashboard">Dashboard</Link>
        <Link href="/alerts">Alerts</Link>
        {isAdmin && <Link href="/admin">Admin</Link>}
      </div>
      {user && (
        <div className="nav-user">
          <span>{user.email}</span>
          <button onClick={handleSignOut}>Sign out</button>
        </div>
      )}
    </nav>
  );
}
