import { Inter } from 'next/font/google';
import { AuthProvider } from '../context/AuthContext';
import '../styles/globals.css';

// Self-hosted at build time (no external request at runtime). Exposed both as an
// actual font-family (.className, so every page inherits it with no extra work) and
// as a --font-inter CSS variable (.variable, so Landing.module.css's --mono/--serif
// tokens can reference the same font instead of each page picking its own).
const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
  variable: '--font-inter',
  display: 'swap',
});

export default function App({ Component, pageProps }) {
  return (
    <div className={`${inter.variable} ${inter.className}`}>
      <AuthProvider>
        <Component {...pageProps} />
      </AuthProvider>
    </div>
  );
}
