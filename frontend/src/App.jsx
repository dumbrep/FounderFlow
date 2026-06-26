import React, { useState, useEffect, useRef } from 'react';
import { Send, Terminal, AlertCircle, Loader2, Sparkles, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import AuthPage from './AuthPage';

const Message = ({ role, content, approvalSummary }) => {
  const isUser = role === 'user';
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={`message-wrapper wrapper-${role}`}
    >
      <div className="msg-row">
        <div className={`avatar ${isUser ? 'avatar-user' : 'avatar-ai'}`}>
          {isUser ? 'You' : <Sparkles size={18} />}
        </div>
        {content && (
          <div className="bubble">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
      </div>
      {approvalSummary && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.15 }}
          className="verification-card"
          style={{ marginTop: '16px', marginLeft: '50px' }}
        >
          <div className="card-label">
            <Terminal size={14} />
            Proposed Action Preview
          </div>
          <div className="data-preview" style={{ whiteSpace: 'pre-wrap' }}>
            <ReactMarkdown>{approvalSummary}</ReactMarkdown>
          </div>
          <div style={{ marginTop: '15px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: 'var(--primary)', backgroundColor: 'rgba(99, 102, 241, 0.08)', padding: '12px', borderRadius: '10px', fontWeight: 500 }}>
            <AlertCircle size={16} />
            <span>Type <b>"yes"</b> to proceed or just tell me what to change!</span>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
};

const WelcomeHero = () => (
  <motion.div
    initial={{ opacity: 0, y: 16 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, ease: 'easeOut' }}
    className="welcome-hero"
  >
    <h1>Welcome to <span className="highlight">FounderFlow</span>.</h1>
    <p>
      I'm your high-performance AI assistant. I can manage your
      <span className="highlight"> Email</span>,
      <span className="highlight"> Google Calendar</span>, and
      <span className="highlight"> Instagram</span> through advanced automated workflows.
    </p>
    <div className="tagline">
      How can I assist you right now?
    </div>
  </motion.div>
);

const TypingIndicator = () => (
  <div className="message-wrapper wrapper-ai">
    <div className="msg-row">
      <div className="avatar avatar-ai">
        <Sparkles size={18} />
      </div>
      <div className="typing-indicator">
        <span className="typing-dot"></span>
        <span className="typing-dot"></span>
        <span className="typing-dot"></span>
      </div>
    </div>
  </div>
);

function App() {
  const [user, setUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const chatContainerRef = useRef(null);

  useEffect(() => {
    const stored = localStorage.getItem('founderflow_user');
    if (stored) {
      try { setUser(JSON.parse(stored)); } catch { localStorage.removeItem('founderflow_user'); }
    }
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const handleAuth = (userData) => setUser(userData);

  const handleLogout = () => {
    fetch('http://localhost:8080/logout', { method: 'POST' }).catch(() => {});
    localStorage.removeItem('founderflow_user');
    setUser(null);
    setMessages([]);
    setSessionId(null);
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userQuery = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: userQuery }]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8080/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userQuery,
          session_id: sessionId
        })
      });

      const data = await response.json();
      setSessionId(data.session_id);

      const processed = data.message.toLowerCase().includes("sent") || data.message.toLowerCase().includes("scheduled");

      setMessages(prev => [...prev, {
        role: 'ai',
        content: processed ? `✅ **Success:** ${data.message}` : data.message,
        approvalSummary: data.needs_approval ? data.approval_summary : null
      }]);

    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'ai',
        content: "### ❌ Critical Error\nCannot communicate with FounderFlow engine. Ensure the server is running on port 8005."
      }]);
    } finally {
      setLoading(false);
    }
  };

  if (!user) {
    return <AuthPage onAuth={handleAuth} />;
  }

  return (
    <div className="app-window">
      <header>
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5 }}
          className="brand-logo"
        >
          FounderFlow
        </motion.div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            className="status-pill"
          >
            <div className="pulse-dot"></div>
            {user.username}
          </motion.div>
          <button
            className="logout-btn"
            onClick={handleLogout}
            title="Logout"
            aria-label="Logout"
          >
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <div className="chat-container" ref={chatContainerRef}>
        <WelcomeHero />
        <AnimatePresence>
          {messages.map((msg, idx) => (
            <Message key={idx} {...msg} />
          ))}
        </AnimatePresence>
        {loading && <TypingIndicator />}
      </div>

      <div className="input-wrapper">
        <input
          type="text"
          className="main-input"
          placeholder="Ask for a draft, a meeting, or a post..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSend()}
          disabled={loading}
        />
        <button
          className="action-button"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          aria-label="Send message"
        >
          {loading ? <Loader2 className="spinner" /> : <Send size={24} />}
        </button>
      </div>
    </div>
  );
}

export default App;
