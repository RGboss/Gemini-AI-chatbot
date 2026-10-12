import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { api } from './api.js';

const suggestions = [
  { label: 'Find the right words', text: 'Help me write a clear, professional email. Ask me what it should be about.', icon: 'write' },
  { label: 'Make something click', text: 'Explain a complex topic simply. Ask me what I would like to learn.', icon: 'idea' },
  { label: 'Build with confidence', text: 'Help me solve a coding problem. Ask me about my language and what I am building.', icon: 'code' },
  { label: 'Explore a new idea', text: 'Help me brainstorm a creative side project. Ask me about my interests.', icon: 'spark' },
];

function Icon({ name, size = 20 }) {
  const paths = {
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="m5 12 7-7 7 7M12 5v14" />,
    chat: <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H4l1.5-4A7.5 7.5 0 1 1 20 11.5Z" />,
    trash: <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></>,
    logout: <path d="M9 4H4v16h5M13 8l4 4-4 4M8 12h13" />,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /></>,
    write: <path d="m15 4 5 5-11 11H4v-5ZM13 6l5 5" />,
    idea: <><path d="M9 18h6M10 21h4M8 14a6 6 0 1 1 8 0l-1 4H9Z" /></>,
    code: <path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Brand() {
  return <div className="brand"><span className="brand-mark"><Icon name="spark" size={24} /></span><span>orbit<span className="brand-dot">.</span></span></div>;
}

function Auth({ onSignIn }) {
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const user = await api(`/auth/${register ? 'register' : 'login'}`, {
        method: 'POST', body: JSON.stringify({ username, password }),
      });
      onSignIn(user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-layout">
      <section className="auth-story">
        <Brand />
        <div className="auth-story-content">
          <div className="eyebrow">A LITTLE CURIOSITY. ENDLESS POSSIBILITIES.</div>
          <h1>Your next big idea<br />starts with a<br /><span>conversation.</span></h1>
          <p>A thoughtful space to write, learn, build, and explore.<br />Powered by Google Gemini. Made for you.</p>
          <div className="orbit-art" aria-hidden="true"><div /><div /><span><Icon name="spark" size={42} /></span></div>
        </div>
        <small>Your conversations, all in one place.</small>
      </section>
      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <div className="eyebrow">YOUR PERSONAL AI WORKSPACE</div>
          <h2>{register ? 'Make room for ideas.' : 'Welcome back.'}</h2>
          <p>{register ? 'Create an account to start your first conversation.' : 'Sign in and pick up where you left off.'}</p>
          <label htmlFor="username">Username</label>
          <input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your username" minLength={3} maxLength={32} pattern={'[a-zA-Z0-9_\\-]+'} title="3-32 letters, numbers, underscores, or hyphens" disabled={busy} required />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" minLength={8} maxLength={128} disabled={busy} required />
          {register && <small className="field-help">Use a unique password with at least 8 characters.</small>}
          {error && <div className="error" role="alert">{error}</div>}
          <button className="primary auth-submit" disabled={busy}>{busy ? 'One moment...' : register ? 'Create account' : 'Sign in'}<Icon name="arrow" size={18} /></button>
          <div className="auth-switch">{register ? 'Already have an account?' : 'New to Orbit?'} <button type="button" disabled={busy} onClick={() => { setRegister(!register); setError(''); }}>{register ? 'Sign in' : 'Create an account'}</button></div>
          <div className="auth-note"><Icon name="chat" size={16} /> Saved history. A space of your own.</div>
        </form>
      </section>
    </main>
  );
}

function Chat({ user, onSignOut }) {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pendingText, setPendingText] = useState('');
  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const operationRef = useRef(false);

  function handleError(err) {
    if (err.status === 401) onSignOut();
    else setError(err.message);
  }

  useEffect(() => {
    let cancelled = false;
    api('/conversations').then((items) => {
      if (!cancelled) setConversations(items);
    }).catch((err) => {
      if (!cancelled) handleError(err);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (messages.length || pendingText) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    } else {
      scrollRef.current?.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, [messages, pendingText]);

  function newChat() {
    setActiveId(null);
    setMessages([]);
    setDraft('');
    setError('');
    setSidebarOpen(false);
    inputRef.current?.focus();
  }

  async function selectChat(id) {
    if (operationRef.current) return;
    operationRef.current = true;
    setBusy(true);
    setError('');
    try {
      const conversation = await api(`/conversations/${id}`);
      setActiveId(id);
      setMessages(conversation.messages);
      setDraft('');
      setSidebarOpen(false);
    } catch (err) {
      handleError(err);
    } finally {
      operationRef.current = false;
      setBusy(false);
    }
  }

  async function removeChat(conversation) {
    if (!window.confirm(`Delete "${conversation.title}"? This cannot be undone.`)) return;
    if (operationRef.current) return;
    operationRef.current = true;
    setBusy(true);
    setError('');
    try {
      await api(`/conversations/${conversation.id}`, { method: 'DELETE' });
      setConversations((items) => items.filter((item) => item.id !== conversation.id));
      if (activeId === conversation.id) newChat();
    } catch (err) {
      handleError(err);
    } finally {
      operationRef.current = false;
      setBusy(false);
    }
  }

  async function send(event) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || operationRef.current) return;
    operationRef.current = true;
    setBusy(true);
    setError('');
    setPendingText(content);
    setDraft('');
    try {
      let id = activeId;
      if (!id) {
        const conversation = await api('/conversations', { method: 'POST' });
        id = conversation.id;
        setActiveId(id);
        setConversations((items) => [conversation, ...items]);
      }
      const result = await api(`/conversations/${id}/messages`, {
        method: 'POST', body: JSON.stringify({ content }),
      });
      setMessages((items) => [...items, ...result.messages]);
      setConversations((items) => [result.conversation, ...items.filter((item) => item.id !== id)]);
    } catch (err) {
      setDraft(content);
      handleError(err);
    } finally {
      setPendingText('');
      operationRef.current = false;
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  async function logout() {
    if (operationRef.current) return;
    operationRef.current = true;
    setBusy(true);
    try {
      await api('/auth/logout', { method: 'POST' });
      onSignOut();
    } catch (err) {
      handleError(err);
    } finally {
      operationRef.current = false;
      setBusy(false);
    }
  }

  const active = conversations.find((item) => item.id === activeId);
  const empty = messages.length === 0 && !pendingText;

  return (
    <div className="workspace">
      {sidebarOpen && <button className="sidebar-overlay" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="sidebar-brand"><Brand /><button className="icon-button mobile-only" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)}><Icon name="close" /></button></div>
        <button className="new-chat" onClick={newChat} disabled={busy || loading}><Icon name="plus" />New conversation</button>
        <div className="history-label">YOUR CONVERSATIONS <span>{conversations.length}</span></div>
        <nav className="history" aria-label="Saved conversations">
          {loading ? <p className="history-empty">Loading conversations...</p> : conversations.length === 0 ? <p className="history-empty">A fresh start.<br />Your conversations will appear here.</p> : conversations.map((item) => (
            <div className={`history-row ${activeId === item.id ? 'selected' : ''}`} key={item.id}>
              <button className="history-item" disabled={busy} onClick={() => selectChat(item.id)} title={item.title}><Icon name="chat" size={17} /><span>{item.title}</span></button>
              <button className="delete-chat" disabled={busy} onClick={() => removeChat(item)} aria-label={`Delete ${item.title}`}><Icon name="trash" size={15} /></button>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="powered"><span className="status-dot" />Powered by Google Gemini</div>
          <div className="user-menu"><span className="avatar">{user.username.slice(0, 2).toUpperCase()}</span><div><strong>{user.username}</strong><small>Personal workspace</small></div><button className="icon-button" onClick={logout} disabled={busy} aria-label="Sign out" title="Sign out"><Icon name="logout" size={19} /></button></div>
        </div>
      </aside>
      <main className="chat-main">
        <header className="chat-header">
          <div><button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar"><Icon name="menu" /></button><span>{active?.title || 'Your space to explore'}</span></div>
          <span className="model-badge"><span className="status-dot" />Gemini</span>
        </header>
        <div ref={scrollRef} className={`chat-scroll ${empty ? 'empty-scroll' : ''}`}>
          {empty ? (
            <section className="welcome">
              <div className="welcome-mark"><Icon name="spark" size={35} /></div>
              <div className="eyebrow">GOOD IDEAS START HERE</div>
              <h1>A little help.<br /><span>A lot of possibility.</span></h1>
              <p>What's on your mind, {user.username}?<br />Let's turn your questions into something great.</p>
              <div className="suggestions">
                {suggestions.map((item) => <button key={item.label} disabled={busy || loading} onClick={() => { setDraft(item.text); inputRef.current?.focus(); }}><Icon name={item.icon} /><span>{item.label}</span><span className="suggestion-arrow">&rarr;</span></button>)}
              </div>
            </section>
          ) : (
            <div className="message-list" aria-live="polite" aria-busy={Boolean(pendingText)}>
              {messages.map((message) => <MessageBubble key={message.id} role={message.role} content={message.content} username={user.username} />)}
              {pendingText && <><MessageBubble role="user" content={pendingText} username={user.username} /><div className="thinking"><span className="assistant-avatar"><Icon name="spark" size={18} /></span><span>Gemini is thinking<span className="thinking-dots">...</span></span></div></>}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        <div className="composer-area">
          {error && <div className="error chat-error" role="alert">{error}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><Icon name="close" size={17} /></button></div>}
          <form className="composer" onSubmit={send}>
            <textarea ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask anything. Start something." aria-label="Message Gemini" rows={2} maxLength={8000} disabled={busy || loading} onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (!busy && !loading) e.currentTarget.form.requestSubmit();
              }
            }} />
            <div className="composer-footer"><span><Icon name="spark" size={14} />A conversation, not just an answer.</span><div><span className="char-count">{draft.length > 7000 ? `${draft.length}/8000` : 'Shift + Enter for a new line'}</span><button className="send-button" aria-label="Send message" disabled={!draft.trim() || busy || loading}><Icon name="arrow" size={21} /></button></div></div>
          </form>
          <p className="disclaimer">AI can make mistakes. Double-check important information.</p>
        </div>
      </main>
    </div>
  );
}

function MessageBubble({ role, content, username }) {
  const assistant = role === 'assistant';
  return (
    <article className={`message ${assistant ? 'assistant' : 'user'}`}>
      <div className={assistant ? 'assistant-avatar' : 'message-avatar'}>{assistant ? <Icon name="spark" size={18} /> : username[0].toUpperCase()}</div>
      <div className="message-body"><div className="message-author">{assistant ? 'Orbit' : 'You'}{assistant && <span>Gemini</span>}</div><div className="message-content">{assistant ? <Markdown>{content}</Markdown> : <p className="user-text">{content}</p>}</div></div>
    </article>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [startupError, setStartupError] = useState('');

  async function checkSession() {
    setChecking(true);
    setStartupError('');
    try {
      setUser(await api('/auth/me'));
    } catch (err) {
      if (err.status !== 401) setStartupError(err.message);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => { checkSession(); }, []);

  if (checking) return <div className="startup"><Brand /><p>Opening your workspace...</p></div>;
  if (startupError) return <div className="startup"><Brand /><div className="error" role="alert">{startupError}</div><button className="primary" onClick={checkSession}>Try again</button></div>;
  return user ? <Chat key={user.id} user={user} onSignOut={() => setUser(null)} /> : <Auth onSignIn={setUser} />;
}
