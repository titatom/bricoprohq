import Link from 'next/link';
import { useRouter } from 'next/router';
import { useAuth } from '../context/AuthContext';

const NAV = [
  { href: '/', label: 'Dashboard', icon: '🏠' },
  { href: '/social-studio', label: 'Social Studio', icon: '✨' },
  { href: '/publishing', label: 'Publishing', icon: '📅' },
  { href: '/kpi', label: 'KPI', icon: '📈' },
  { href: '/settings', label: 'Settings', icon: '⚙️' },
];

function BrandMark({ size = 'md' }) {
  const dimensions = size === 'lg' ? 'w-20 h-20 text-2xl' : 'w-11 h-11 text-base';

  return (
    <div className={`${dimensions} bg-accent-500 rounded-2xl flex items-center justify-center shadow-sm`}>
      <div className="w-3/4 h-3/4 bg-brand-600 rounded-xl flex items-center justify-center border-2 border-white/85">
        <span className="text-white font-black tracking-tighter leading-none">BP</span>
      </div>
    </div>
  );
}

export default function Layout({ children }) {
  const { isLoggedIn, logout, user } = useAuth();
  const router = useRouter();

  if (!isLoggedIn) return <>{children}</>;

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="w-20 bg-brand-600 flex flex-col flex-shrink-0">

        <div className="px-4 py-5 border-b border-brand-700 flex justify-center">
          <BrandMark />
        </div>

        <nav className="flex-1 py-4 overflow-y-auto space-y-2">
          {NAV.map(({ href, label, icon }) => {
            const active = router.pathname === href;
            return (
              <Link
                key={href}
                href={href}
                aria-label={label}
                title={label}
                className={`mx-auto w-12 h-12 rounded-2xl flex items-center justify-center text-xl transition-colors ${
                  active
                    ? 'bg-accent-500 text-white shadow-lg shadow-black/10'
                    : 'text-brand-100 hover:bg-brand-700 hover:text-white'
                }`}
              >
                <span className="text-base">{icon}</span>
              </Link>
            );
          })}
        </nav>

        <div className="px-3 py-4 border-t border-brand-700">
          <button
            onClick={logout}
            className="w-12 h-12 mx-auto rounded-2xl text-brand-200 hover:text-white hover:bg-brand-700 transition-colors flex items-center justify-center"
            title={`Sign out ${user?.email || ''}`}
            aria-label="Sign out"
          >
            →
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto bg-gray-50">
        {children}
      </main>
    </div>
  );
}
