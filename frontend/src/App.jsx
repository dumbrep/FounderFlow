import React, { useState, useEffect, useRef } from 'react';
import { Send, Terminal, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';

const Message = ({ role, content, approvalSummary }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className={`message-wrapper wrapper-${role}`}
    >
      {content && (
        <div className="bubble">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
      {approvalSummary && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="verification-card"
          style={{ marginTop: '16px' }}
        >
          <div className="card-label">
            <Terminal size={14} />
            Proposed Action Preview
          </div>
          <div className="data-preview" style={{ fontFamily: 'Inter', whiteSpace: 'pre-wrap' }}>
            <ReactMarkdown>{approvalSummary}</ReactMarkdown>
          </div>
          <div style={{ marginTop: '15px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: '#a5b4fc', backgroundColor: 'rgba(165, 180, 252, 0.1)', padding: '10px', borderRadius: '8px' }}>
            <AlertCircle size={16} />
            <span>Type <b>"yes"</b> to proceed or just tell me what to change!</span>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
};

const WelcomeHero = () => (
  <div className="welcome-hero">
    <h1>Welcome to <span className="highlight">FounderFlow</span>.</h1>
    <p>
      I'm your high-performance AI assistant. I can manage your
      <span className="highlight"> Email</span>,
      <span className="highlight"> Google Calendar</span>, and
      <span className="highlight"> Instagram</span> through advanced automated workflows.
    </p>
    <div style={{ marginTop: '18px', fontSize: '15px', color: '#a5b4fc', fontWeight: '500' }}>
      How can I assist you right now?
    </div>
  </div>
);

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const chatContainerRef = useRef(null);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userQuery = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: userQuery }]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8005/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userQuery,
          session_id: sessionId
        })
      });

      const data = await response.json();
      setSessionId(data.session_id);

      // If the message is "Task processed." or similar, show a special success indicator
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

  return (
    <div className="app-window">
      <header>
        <div className="brand-logo">FounderFlow</div>
        <div className="status-pill">
          <div className="pulse-dot"></div>
          System Active
        </div>
      </header>

      <div className="chat-container" ref={chatContainerRef}>
        <WelcomeHero />
        <AnimatePresence>
          {messages.map((msg, idx) => (
            <Message key={idx} {...msg} />
          ))}
        </AnimatePresence>
        {loading && (
          <div className="message-wrapper wrapper-ai">
            <div className="bubble" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 20px' }}>
              <Loader2 className="spinner" size={18} />
              <span>Processing...</span>
            </div>
          </div>
        )}
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
        >
          {loading ? <Loader2 className="spinner" /> : <Send size={24} />}
        </button>
      </div>
    </div>
  );
}

export default App;
