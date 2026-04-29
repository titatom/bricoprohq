import { useMemo, useState } from 'react';
const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const sources = ['google_calendar', 'jobber', 'immich', 'paperless'];

export default function Home() {
  const [token, setToken] = useState('');
  const [email, setEmail] = useState('admin@bricopro.local');
  const [password, setPassword] = useState('admin1234');
  const [dashboard, setDashboard] = useState({});
  const [integrations, setIntegrations] = useState([]);
  const [status, setStatus] = useState('Ready');

  const authHeader = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const authedFetch = (url, options = {}) => fetch(url, { ...options, headers: { ...(options.headers || {}), ...authHeader } });

  const login = async () => {
    const r = await fetch(`${api}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
    if (!r.ok) return setStatus('Login failed');
    const data = await r.json(); setToken(data.access_token || ''); setStatus('Logged in');
  };

  const loadDashboard = async () => {
    const r = await authedFetch(`${api}/dashboard`); const data = await r.json(); setDashboard(data);
  };
  const loadIntegrations = async () => {
    const r = await authedFetch(`${api}/integrations`); setIntegrations(await r.json());
  };

  const refreshSource = async (source) => {
    setStatus(`Refreshing ${source}...`);
    const r = await authedFetch(`${api}/dashboard/refresh/${source}`, { method: 'POST' });
    const result = await r.json();
    setStatus(result.status === 'ok' ? `Refreshed ${source}` : `Widget error: ${result.error}`);
    await loadDashboard(); await loadIntegrations();
  };

  return (
    <main style={{ fontFamily: 'Arial, sans-serif', margin: '2rem' }}>
      <h1>Bricopro HQ — Milestone 2</h1><p>Status: {status}</p>
      <section><h3>Login</h3><input value={email} onChange={(e)=>setEmail(e.target.value)} /><input type="password" value={password} onChange={(e)=>setPassword(e.target.value)} /><button onClick={login}>Login</button></section>
      <section><h3>Dashboard</h3><button disabled={!token} onClick={loadDashboard}>Load Dashboard</button>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginTop:12 }}>
          {sources.map((src)=>{
            const w = dashboard[src] || { warning: 'No data' };
            return <div key={src} style={{ border:'1px solid #ddd', padding:10 }}><strong>{src}</strong> {w.stale ? <span style={{color:'darkorange'}}> (stale)</span> : null}<div><button disabled={!token} onClick={()=>refreshSource(src)}>Refresh</button></div><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(w, null, 2)}</pre></div>;
          })}
        </div>
      </section>
      <section><h3>Integration Status</h3><button disabled={!token} onClick={loadIntegrations}>Load Integrations</button><pre>{JSON.stringify(integrations, null, 2)}</pre></section>
    </main>
  );
}
