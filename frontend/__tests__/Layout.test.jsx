import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

jest.mock('next/link', () => {
  // Forward all props so aria-label, title, className, etc. are preserved.
  const Link = ({ children, href, ...rest }) => <a href={href} {...rest}>{children}</a>;
  Link.displayName = 'Link';
  return Link;
});
jest.mock('next/router', () => ({
  useRouter: () => ({ pathname: '/' }),
}));
jest.mock('../context/AuthContext', () => ({
  useAuth: () => ({ isLoggedIn: true, logout: jest.fn(), user: { email: 'admin@bricopro.local' } }),
}));

import Layout from '../components/Layout';

describe('Layout sidebar', () => {
  it('renders all four primary nav links', () => {
    render(<Layout><div>content</div></Layout>);
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /social studio/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /kpi/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument();
  });

  it('does not expose direct nav links to /queues, /publishing, or /campaigns', () => {
    render(<Layout><div>content</div></Layout>);
    const links = screen.getAllByRole('link');
    const hrefs = links.map((l) => l.getAttribute('href'));
    expect(hrefs).not.toContain('/queues');
    expect(hrefs).not.toContain('/publishing');
    expect(hrefs).not.toContain('/campaigns');
  });

  it('renders a sign-out button', () => {
    render(<Layout><div>content</div></Layout>);
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
  });

  it('renders children inside the main content area', () => {
    render(<Layout><p>hello world</p></Layout>);
    expect(screen.getByText('hello world')).toBeInTheDocument();
  });
});
