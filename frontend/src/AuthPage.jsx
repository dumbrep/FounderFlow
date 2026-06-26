import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Lock, User, LogIn, Sparkles } from 'lucide-react';

export default function AuthPage({ onAuth }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ username: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const endpoint = mode === 'login' ? '/login' : '/signup';
    const body = mode === 'login'
      ? { email: form.email, password: form.password }
      : { username: form.username, email: form.email, password: form.password };

    try {
      const res = await fetch(`http://localhost:8080${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Something went wrong');
      }

      const user = await res.json();
      localStorage.setItem('founderflow_user', JSON.stringify(user));
      onAuth(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setMode(m => m === 'login' ? 'signup' : 'login');
    setError('');
  };

  return (
    <div className="auth-page">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="auth-card"
      >
        <div className="auth-header">
          <div className="auth-logo">
            <Sparkles size={28} />
          </div>
          <h1>FounderFlow</h1>
          <p>{mode === 'login' ? 'Welcome back' : 'Create your account'}</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <AnimatePresence mode="wait">
            {mode === 'signup' && (
              <motion.div
                key="username"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="input-group"
              >
                <User size={18} className="input-icon" />
                <input
                  type="text"
                  placeholder="Username"
                  value={form.username}
                  onChange={e => setForm({ ...form, username: e.target.value })}
                  required
                  disabled={loading}
                />
              </motion.div>
            )}
          </AnimatePresence>

          <div className="input-group">
            <Mail size={18} className="input-icon" />
            <input
              type="email"
              placeholder="Email"
              value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
              required
              disabled={loading}
            />
          </div>

          <div className="input-group">
            <Lock size={18} className="input-icon" />
            <input
              type="password"
              placeholder="Password"
              value={form.password}
              onChange={e => setForm({ ...form, password: e.target.value })}
              required
              minLength={6}
              disabled={loading}
            />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="auth-error"
            >
              {error}
            </motion.div>
          )}

          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? (
              <span className="spinner" style={{ width: 20, height: 20, borderWidth: 2 }} />
            ) : (
              <>{mode === 'login' ? <LogIn size={20} /> : <User size={20} />}
                {mode === 'login' ? 'Sign In' : 'Create Account'}</>
            )}
          </button>
        </form>

        <div className="auth-footer">
          {mode === 'login' ? (
            <>Don't have an account? <button onClick={toggleMode} className="link-btn">Sign up</button></>
          ) : (
            <>Already have an account? <button onClick={toggleMode} className="link-btn">Sign in</button></>
          )}
        </div>
      </motion.div>
    </div>
  );
}
