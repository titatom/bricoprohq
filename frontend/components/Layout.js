import Link from 'next/link';
import { useRouter } from 'next/router';
import { useAuth } from '../context/AuthContext';

const NAV = [
  { href: '/', label: 'Dashboard', icon: '🏠' },
  { href: '/queues', label: 'Queues', icon: '📋' },
  { href: '/social-studio', label: 'Social Studio', icon: '✨' },
  { href: '/publishing', label: 'Publishing', icon: '📅' },
  { href: '/campaigns', label: 'Campaigns', icon: '🎯' },
  { href: '/settings', label: 'Settings', icon: '⚙️' },
];

export default function Layout({ children }) {
  const { isLoggedIn, logout, user } = useAuth();
  const router = useRouter();

  if (!isLoggedIn) return <>{children}</>;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar — navy */}
      <aside className="w-56 bg-brand-600 flex flex-col flex-shrink-0">

        {/* Logo lockup */}
        <div className="px-5 py-4 border-b border-brand-700">
          {/* BP monogram box — mirrors the icon logo */}
          <div className="flex items-center gap-3 mb-1">
            <div className="flex-shrink-0 w-9 h-9 bg-accent-500 rounded flex items-center justify-center border-2 border-accent-500 shadow-sm">
              <span className="text-white font-black text-sm tracking-tighter leading-none">BP</span>
            </div>
            <div>
              <h1 className="text-white font-bold text-base leading-tight tracking-wide">BRICOPRO</h1>
              <p className="text-brand-200 text-xs leading-tight">HQ</p>
            </div>
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {NAV.map(({ href, label, icon }) => {
            const active = router.pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
                  active
                    ? 'bg-brand-700 text-white font-semibold border-l-2 border-accent-500'
                    : 'text-brand-100 hover:bg-brand-700 hover:text-white border-l-2 border-transparent'
                }`}
              >
                <span className="text-base">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-brand-700">
          <p className="text-brand-200 text-xs truncate mb-2 opacity-80">{user?.email || 'admin'}</p>
          <button
            onClick={logout}
            className="w-full text-xs text-brand-200 hover:text-accent-400 py-1 text-left transition-colors"
          >
            Sign out →
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-gray-50">
        {children}
      </main>
    </div>
  );
}
