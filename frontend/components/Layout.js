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
      {/* Sidebar */}
      <aside className="w-56 bg-brand-900 flex flex-col flex-shrink-0">
        <div className="px-5 py-4 border-b border-brand-700">
          <h1 className="text-white font-bold text-lg leading-tight">Bricopro HQ</h1>
          <p className="text-brand-100 text-xs mt-0.5 opacity-75">Business Command Center</p>
        </div>
        <nav className="flex-1 py-3 overflow-y-auto">
          {NAV.map(({ href, label, icon }) => {
            const active = router.pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
                  active
                    ? 'bg-brand-700 text-white font-medium'
                    : 'text-brand-100 hover:bg-brand-800 hover:text-white'
                }`}
              >
                <span className="text-base">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="px-5 py-4 border-t border-brand-700">
          <p className="text-brand-100 text-xs truncate mb-2">{user?.email || 'admin'}</p>
          <button
            onClick={logout}
            className="w-full text-xs text-brand-100 hover:text-white py-1 text-left transition-colors"
          >
            Sign out
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
