import { createContext, useContext, useState, useCallback } from 'react';

const AuthContext = createContext(null);

export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() =>
    typeof window !== 'undefined' ? localStorage.getItem('hq_token') || '' : ''
  );
  const [user, setUser] = useState(null);

  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  const apiFetch = useCallback(async (path, options = {}) => {
    const res = await fetch(`${API}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...authHeader, ...(options.headers || {}) },
    });
    if (res.status === 401) {
      setToken(''); setUser(null);
      if (typeof window !== 'undefined') localStorage.removeItem('hq_token');
    }
    return res;
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (email, password) => {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error('Invalid credentials');
    const data = await res.json();
    setToken(data.access_token);
    if (typeof window !== 'undefined') localStorage.setItem('hq_token', data.access_token);
    setUser({ email });
    return data;
  }, []);

  const logout = useCallback(() => {
    setToken(''); setUser(null);
    if (typeof window !== 'undefined') localStorage.removeItem('hq_token');
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, login, logout, apiFetch, isLoggedIn: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
