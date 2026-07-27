import { useEffect } from 'react';
import { useRouter } from 'next/router';
import { useAuth } from '../context/AuthContext';

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.push(user ? '/dashboard' : '/signin');
  }, [user, loading, router]);

  return <p style={{ textAlign: 'center', marginTop: 80 }}>Loading...</p>;
}
