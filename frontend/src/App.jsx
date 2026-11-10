import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { api } from './api.js';

const suggestions = [
  {
    label: 'Document Intelligence',
    desc: 'Upload a PDF to interrogate, extract, and analyze',
    action: 'upload',
    text: '',
    icon: 'file',
  },
  {
    label: 'Deep Architecture',
    desc: 'Design resilient system architectures and code',
    text: 'Help me architect a full-stack application. Ask me about my tech stack and requirements.',
    icon: 'code',
  },
  {
    label: 'First Principles',
    desc: 'Deconstruct complex topics into fundamentals',
    text: 'Explain a complex concept using first principles. Ask me what topic I want to explore.',
    icon: 'compass',
  },
  {
    label: 'Strategic Roadmap',
    desc: 'Synthesize goals into clear execution milestones',
    text: 'Help me build a structured strategic execution plan. Ask me what I am building.',
    icon: 'zap',
  },
];

function Icon({ name, size = 20 }) {
  const paths = {
    orbit: (
      <>
        <circle cx="12" cy="12" r="4" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.7" />
        <ellipse cx="12" cy="12" rx="9" ry="3.5" transform="rotate(-28 12 12)" stroke="currentColor" strokeWidth="1.7" />
        <circle cx="18.5" cy="8.2" r="1.3" fill="currentColor" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    chat: <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />,
    trash: (
      <>
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        <line x1="10" y1="11" x2="10" y2="17" />
        <line x1="14" y1="11" x2="14" y2="17" />
      </>
    ),
    logout: (
      <>
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
        <polyline points="16 17 21 12 16 7" />
        <line x1="21" y1="12" x2="9" y2="12" />
      </>
    ),
    code: (
      <>
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </>
    ),
    compass: (
      <>
        <circle cx="12" cy="12" r="10" />
        <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
      </>
    ),
    zap: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />,
    write: (
      <>
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </>
    ),
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="M18 6L6 18M6 6l12 12" />,
    send: (
      <>
        <line x1="22" y1="2" x2="11" y2="13" />
        <polygon points="22 2 15 22 11 13 2 9 22 2" />
      </>
    ),
    paperclip: (
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    ),
    file: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </>
    ),
    copy: (
      <>
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
      </>
    ),
    check: <polyline points="20 6 9 17 4 12" />,
    refresh: (
      <>
        <polyline points="23 4 23 10 17 10" />
        <polyline points="1 20 1 14 7 14" />
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
      </>
    ),
    download: (
      <>
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </>
    ),
    columns: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <line x1="12" y1="3" x2="12" y2="21" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Icon name="orbit" size={26} />
      </span>
      <span className="brand-text">
        orbit<span className="brand-dot">·</span>
      </span>
    </div>
  );
}

function formatCitations(text, defaultDoc) {
  if (!text) return '';
  // Transform [Document: filename.pdf | Page: 2] or [Document: filename.pdf, Page 2] into clickable markdown links
  let formatted = text.replace(
    /\[(?:Document|Source):\s*([^,\]|]+)(?:[,|]\s*Page:?\s*(\d+))?[^\]]*\]/gi,
    (match, doc, page) => {
      const p = page || '1';
      const cleanDoc = doc.trim();
      return `[📄 ${cleanDoc} (Page ${p})](#citation:${cleanDoc}:${p})`;
    }
  );
  // Transform standalone [Page 2] or [Page: 2]
  formatted = formatted.replace(/\[Page:?\s*(\d+)\]/gi, (match, page) => {
    const doc = defaultDoc || 'Document';
    return `[📄 Page ${page}](#citation:${doc}:${page})`;
  });
  return formatted;
}

function DocumentViewer({ filename, conversationId, targetPage, onClose }) {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    if (!filename || !conversationId) return;
    setLoading(true);
    api(`/conversations/${conversationId}/documents/${encodeURIComponent(filename)}/content`)
      .then((res) => {
        setPages(res.pages || []);
      })
      .catch(() => setPages([]))
      .finally(() => setLoading(false));
  }, [filename, conversationId]);

  useEffect(() => {
    if (targetPage && !loading) {
      setTimeout(() => {
        const el = document.getElementById(`doc-page-${targetPage}`);
        el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
    }
  }, [targetPage, loading]);

  const filteredPages = pages.filter((p) =>
    searchTerm ? p.text.toLowerCase().includes(searchTerm.toLowerCase()) : true
  );

  return (
    <aside className="doc-viewer-panel" aria-label="Document Viewer">
      <div className="doc-viewer-header">
        <div className="doc-viewer-title">
          <Icon name="file" size={17} />
          <span title={filename}>{filename}</span>
        </div>
        <div className="doc-viewer-controls">
          <div className="doc-search-box">
            <Icon name="search" size={13} />
            <input
              type="text"
              placeholder="Find in document..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close document viewer">
            <Icon name="close" size={16} />
          </button>
        </div>
      </div>

      <div className="doc-viewer-body">
        {loading ? (
          <div className="doc-viewer-loading">
            <span className="loading-orbit-ring" />
            <p>Rendering pages...</p>
          </div>
        ) : pages.length === 0 ? (
          <div className="doc-viewer-empty">
            <p>No selectable text available for this document.</p>
          </div>
        ) : (
          filteredPages.map((page) => (
            <section
              key={page.page}
              id={`doc-page-${page.page}`}
              className={`doc-page-card ${targetPage === page.page ? 'target-highlight' : ''}`}
            >
              <header className="doc-page-badge">
                <span>PAGE {page.page}</span>
                {targetPage === page.page && <span className="citation-target-pill">Referenced Citation</span>}
              </header>
              <div className="doc-page-text">{page.text}</div>
            </section>
          ))
        )}
      </div>
    </aside>
  );
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
        method: 'POST',
        body: JSON.stringify({ username, password }),
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
        <div className="ambient-orb orb-1" />
        <div className="ambient-orb orb-2" />
        <Brand />
        <div className="auth-story-content">
          <div className="eyebrow">ENTERPRISE RAG ARCHITECTURE</div>
          <h1>
            Your enterprise data in<br />
            <span>perpetual orbit.</span>
          </h1>
          <p>
            An advanced cognitive workspace with Hybrid Search (Dense + BM25), Cross-Encoder reranking,
            and split-screen page citation verification.
          </p>
          <div className="orbit-visual" aria-hidden="true">
            <div className="ring ring-outer" />
            <div className="ring ring-mid" />
            <div className="ring ring-inner" />
            <div className="orbit-core">
              <Icon name="orbit" size={46} />
            </div>
          </div>
        </div>
        <small className="auth-footer-tag">Orbit AI Workspace · Enterprise v2.5</small>
      </section>

      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <div className="eyebrow">SECURE ACCESS</div>
          <h2>{register ? 'Initialize Orbit' : 'Welcome back'}</h2>
          <p>
            {register
              ? 'Create your workspace credentials to get started.'
              : 'Sign in to access your saved orbits and documents.'}
          </p>

          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Choose username"
            minLength={3}
            maxLength={32}
            pattern="[a-zA-Z0-9_\-]+"
            title="3-32 letters, numbers, underscores, or hyphens"
            disabled={busy}
            required
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete={register ? 'new-password' : 'current-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            minLength={8}
            maxLength={128}
            disabled={busy}
            required
          />

          {register && <small className="field-help">Protected with Argon2 encryption.</small>}
          {error && <div className="error" role="alert">{error}</div>}

          <button className="primary auth-submit" disabled={busy}>
            <span>{busy ? 'Verifying...' : register ? 'Create Workspace' : 'Launch Session'}</span>
            <Icon name="arrow" size={18} />
          </button>

          <div className="auth-switch">
            {register ? 'Already have a session?' : 'Need a workspace?'}{' '}
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setRegister(!register);
                setError('');
              }}
            >
              {register ? 'Sign in' : 'Create account'}
            </button>
          </div>

          <div className="auth-note">
            <Icon name="chat" size={15} /> Private vector memory & local session store.
          </div>
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

  // Streaming & RAG states
  const [pendingUserText, setPendingUserText] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadBanner, setUploadBanner] = useState('');

  // Split-screen viewer state
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerDoc, setViewerDoc] = useState('');
  const [targetCitationPage, setTargetCitationPage] = useState(null);

  // Quick action feedback
  const [copiedId, setCopiedId] = useState(null);

  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);
  const operationRef = useRef(false);

  function handleError(err) {
    if (err.status === 401) onSignOut();
    else setError(err.message);
  }

  useEffect(() => {
    let cancelled = false;
    api('/conversations')
      .then((items) => {
        if (!cancelled) setConversations(items);
      })
      .catch((err) => {
        if (!cancelled) handleError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (messages.length || pendingUserText || streamingText) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    } else {
      scrollRef.current?.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, [messages, pendingUserText, streamingText]);

  async function loadDocuments(convId) {
    if (!convId) {
      setDocuments([]);
      return;
    }
    try {
      const res = await api(`/conversations/${convId}/documents`);
      const docs = res.documents || [];
      setDocuments(docs);
      if (docs.length > 0 && !viewerDoc) {
        setViewerDoc(docs[0]);
      }
    } catch {
      setDocuments([]);
    }
  }

  function newChat() {
    setActiveId(null);
    setMessages([]);
    setDraft('');
    setError('');
    setDocuments([]);
    setUploadBanner('');
    setStreamingText('');
    setPendingUserText('');
    setViewerOpen(false);
    setSidebarOpen(false);
    inputRef.current?.focus();
  }

  async function selectChat(id) {
    if (operationRef.current) return;
    operationRef.current = true;
    setBusy(true);
    setError('');
    setUploadBanner('');
    setStreamingText('');
    setPendingUserText('');
    try {
      const conversation = await api(`/conversations/${id}`);
      setActiveId(id);
      setMessages(conversation.messages);
      setDraft('');
      setSidebarOpen(false);
      await loadDocuments(id);
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

  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError('');
    setUploadBanner(`Uploading and indexing "${file.name}" into Qdrant Hybrid Store...`);

    try {
      let id = activeId;
      if (!id) {
        const conversation = await api('/conversations', { method: 'POST' });
        id = conversation.id;
        setActiveId(id);
        setConversations((items) => [conversation, ...items]);
      }

      const formData = new FormData();
      formData.append('file', file);

      const res = await api(`/conversations/${id}/upload`, {
        method: 'POST',
        body: formData,
      });

      const updatedDocs = [...new Set([...documents, res.filename])];
      setDocuments(updatedDocs);
      setViewerDoc(res.filename);
      setUploadBanner(`Indexed "${res.filename}" (${res.chunks_processed} chunks across ${res.pages_count || 1} pages)`);
      setTimeout(() => setUploadBanner(''), 6000);
    } catch (err) {
      setError(err.message);
      setUploadBanner('');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  // Streaming Send Implementation using Server-Sent Events (SSE)
  async function send(event, retryPrompt = null) {
    if (event) event.preventDefault();
    const content = (retryPrompt || draft).trim();
    if (!content || operationRef.current) return;

    operationRef.current = true;
    setBusy(true);
    setError('');
    setPendingUserText(content);
    setStreamingText('');
    setDraft('');

    let id = activeId;
    if (!id) {
      try {
        const conversation = await api('/conversations', { method: 'POST' });
        id = conversation.id;
        setActiveId(id);
        setConversations((items) => [conversation, ...items]);
      } catch (err) {
        handleError(err);
        operationRef.current = false;
        setBusy(false);
        return;
      }
    }

    try {
      const response = await fetch(`/api/conversations/${id}/messages/stream`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to stream response.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let accumulated = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'token') {
                accumulated += data.token;
                setStreamingText(accumulated);
              } else if (data.type === 'done') {
                setMessages((items) => [...items, ...data.messages]);
                setConversations((items) => [
                  data.conversation,
                  ...items.filter((item) => item.id !== id),
                ]);
              } else if (data.type === 'error') {
                throw new Error(data.detail);
              }
            } catch (e) {
              console.error('SSE parse error:', e);
            }
          }
        }
      }
    } catch (err) {
      setDraft(content);
      handleError(err);
    } finally {
      setStreamingText('');
      setPendingUserText('');
      operationRef.current = false;
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function handleCitationClick(docName, pageNum) {
    const targetDoc = docName && docName !== 'Document' ? docName : documents[0] || '';
    setViewerDoc(targetDoc);
    setTargetCitationPage(parseInt(pageNum, 10) || 1);
    setViewerOpen(true);
  }

  function copyToClipboard(text, id) {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  async function handleExportMarkdown() {
    if (!activeId) return;
    try {
      window.open(`/api/conversations/${activeId}/export`, '_blank');
    } catch (err) {
      handleError(err);
    }
  }

  function handleRegenerate() {
    // Find last user message
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        send(null, messages[i].content);
        break;
      }
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
  const empty = messages.length === 0 && !pendingUserText && !streamingText;

  return (
    <div className={`workspace ${viewerOpen ? 'has-split-viewer' : ''}`}>
      {sidebarOpen && (
        <button
          className="sidebar-overlay"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? 'is-open' : ''}`}>
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button mobile-only"
            aria-label="Close sidebar"
            onClick={() => setSidebarOpen(false)}
          >
            <Icon name="close" />
          </button>
        </div>

        <button className="new-chat" onClick={newChat} disabled={busy || loading}>
          <Icon name="plus" size={17} />
          <span>New Session</span>
        </button>

        <div className="history-label">
          <span>SESSIONS</span>
          <span className="count-pill">{conversations.length}</span>
        </div>

        <nav className="history" aria-label="Saved sessions">
          {loading ? (
            <p className="history-empty">Loading sessions...</p>
          ) : conversations.length === 0 ? (
            <p className="history-empty">
              No sessions yet.<br />Initiate a dialogue or upload a document to begin.
            </p>
          ) : (
            conversations.map((item) => (
              <div
                className={`history-row ${activeId === item.id ? 'selected' : ''}`}
                key={item.id}
              >
                <button
                  className="history-item"
                  disabled={busy}
                  onClick={() => selectChat(item.id)}
                  title={item.title}
                >
                  <Icon name="chat" size={15} />
                  <span>{item.title}</span>
                </button>
                <button
                  className="delete-chat"
                  disabled={busy}
                  onClick={() => removeChat(item)}
                  aria-label={`Delete ${item.title}`}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
            ))
          )}
        </nav>

        <div className="sidebar-bottom">
          <div className="powered">
            <span className="status-dot live" />
            <span>Orbit Hybrid RAG + BM25</span>
          </div>
          <div className="user-menu">
            <span className="avatar">{user.username.slice(0, 2).toUpperCase()}</span>
            <div>
              <strong>{user.username}</strong>
              <small>Enterprise Member</small>
            </div>
            <button
              className="icon-button"
              onClick={logout}
              disabled={busy}
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon name="logout" size={18} />
            </button>
          </div>
        </div>
      </aside>

      <div className="workspace-center">
        <main className="chat-main">
          <header className="chat-header">
            <div className="header-left">
              <button
                className="icon-button mobile-only"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
              >
                <Icon name="menu" />
              </button>
              <div className="session-title">
                <span className="session-dot" />
                <span>{active?.title || 'Orbit Workspace'}</span>
              </div>
            </div>

            <div className="header-right">
              {messages.length > 0 && (
                <button
                  type="button"
                  className="header-action-button"
                  onClick={handleExportMarkdown}
                  title="Export conversation as Markdown"
                >
                  <Icon name="download" size={14} />
                  <span>Export</span>
                </button>
              )}

              {documents.length > 0 && (
                <button
                  type="button"
                  className={`header-action-button ${viewerOpen ? 'active' : ''}`}
                  onClick={() => {
                    if (!viewerDoc) setViewerDoc(documents[0]);
                    setViewerOpen(!viewerOpen);
                  }}
                  title="Toggle Split-Screen Document Viewer"
                >
                  <Icon name="columns" size={14} />
                  <span>Split Viewer ({documents.length})</span>
                </button>
              )}

              <span className="orbit-badge">
                <span className="status-dot live" />
                Orbit Core v2.5
              </span>
            </div>
          </header>

          <div ref={scrollRef} className={`chat-scroll ${empty ? 'empty-scroll' : ''}`}>
            {empty ? (
              <section className="welcome">
                <div className="welcome-halo">
                  <div className="welcome-mark">
                    <Icon name="orbit" size={42} />
                  </div>
                </div>
                <div className="eyebrow">ENTERPRISE RAG · HYBRID SEARCH · CITATIONS</div>
                <h1>
                  Hello, <span>{user.username}</span>.
                </h1>
                <p>
                  Orbit is ready. Ask questions, construct architectures, or upload PDFs to interrogate your data with Hybrid Search, BM25 keyword matching, and click-to-verify citations.
                </p>

                <div className="suggestions">
                  {suggestions.map((item) => (
                    <button
                      key={item.label}
                      disabled={busy || loading || uploading}
                      onClick={() => {
                        if (item.action === 'upload') {
                          fileInputRef.current?.click();
                        } else {
                          setDraft(item.text);
                          inputRef.current?.focus();
                        }
                      }}
                    >
                      <div className="suggestion-icon">
                        <Icon name={item.icon} size={18} />
                      </div>
                      <div className="suggestion-body">
                        <strong>{item.label}</strong>
                        <span>{item.desc}</span>
                      </div>
                      <span className="suggestion-arrow">&rarr;</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : (
              <div className="message-list" aria-live="polite">
                {messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    id={message.id}
                    role={message.role}
                    content={message.content}
                    username={user.username}
                    defaultDoc={documents[0]}
                    onCitationClick={handleCitationClick}
                    onCopy={copyToClipboard}
                    copied={copiedId === message.id}
                    onRegenerate={handleRegenerate}
                  />
                ))}

                {pendingUserText && (
                  <MessageBubble
                    role="user"
                    content={pendingUserText}
                    username={user.username}
                    onCitationClick={handleCitationClick}
                  />
                )}

                {streamingText && (
                  <article className="message assistant streaming-message">
                    <div className="assistant-avatar">
                      <Icon name="orbit" size={18} />
                    </div>
                    <div className="message-body">
                      <div className="message-author">
                        <span className="author-name">Orbit</span>
                        <span className="ai-tag live-stream">Streaming</span>
                      </div>
                      <div className="message-content">
                        <Markdown
                          components={{
                            a: ({ href, children }) => {
                              if (href && href.startsWith('#citation:')) {
                                const parts = href.replace('#citation:', '').split(':');
                                return (
                                  <button
                                    type="button"
                                    className="citation-pill"
                                    onClick={() => handleCitationClick(parts[0], parts[1])}
                                  >
                                    {children}
                                  </button>
                                );
                              }
                              return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
                            },
                          }}
                        >
                          {formatCitations(streamingText, documents[0])}
                        </Markdown>
                      </div>
                    </div>
                  </article>
                )}

                {pendingUserText && !streamingText && (
                  <div className="thinking">
                    <span className="assistant-avatar thinking-orbit">
                      <Icon name="orbit" size={18} />
                    </span>
                    <span className="thinking-text">
                      Orbit is reranking & reasoning<span className="thinking-dots">...</span>
                    </span>
                  </div>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="composer-area">
            {uploadBanner && (
              <div className="upload-banner">
                <span className="status-dot live" />
                <span>{uploadBanner}</span>
              </div>
            )}

            {documents.length > 0 && (
              <div className="attached-docs-bar">
                <span className="attached-label">
                  <Icon name="file" size={13} />
                  Active Knowledge:
                </span>
                <div className="docs-chips">
                  {documents.map((doc) => (
                    <button
                      key={doc}
                      type="button"
                      className={`doc-chip ${viewerDoc === doc && viewerOpen ? 'active' : ''}`}
                      onClick={() => {
                        setViewerDoc(doc);
                        setViewerOpen(true);
                      }}
                      title="Click to view in Split Screen"
                    >
                      <Icon name="file" size={12} />
                      <span>{doc}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="error chat-error" role="alert">
                <span>{error}</span>
                <button
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => setError('')}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            )}

            <form className="composer" onSubmit={send}>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept=".pdf,.txt,.md,.csv,.json"
                style={{ display: 'none' }}
                disabled={busy || uploading}
              />

              <textarea
                ref={inputRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Ask anything or interrogate uploaded documents... (Enter to send, Shift + Enter for newline)"
                aria-label="Message Orbit"
                rows={2}
                maxLength={8000}
                disabled={busy || loading || uploading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (!busy && !loading && !uploading) send(e);
                  }
                }}
              />

              <div className="composer-footer">
                <div className="composer-footer-left">
                  <button
                    type="button"
                    className="icon-button attach-button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={busy || uploading}
                    aria-label="Upload document"
                    title="Upload PDF or text document to index into Qdrant"
                  >
                    <Icon name="paperclip" size={17} />
                    <span className="attach-text">{uploading ? 'Indexing...' : 'Attach PDF'}</span>
                  </button>
                  <span className="composer-indicator">
                    <Icon name="orbit" size={13} />
                    Hybrid RAG + SSE Stream
                  </span>
                </div>

                <div className="composer-actions">
                  <span className="char-count">
                    {draft.length > 6000 ? `${draft.length}/8000` : ''}
                  </span>
                  <button
                    className="send-button"
                    aria-label="Send message"
                    disabled={!draft.trim() || busy || loading || uploading}
                  >
                    <Icon name="send" size={16} />
                  </button>
                </div>
              </div>
            </form>
            <p className="disclaimer">Orbit uses Hybrid RAG & Cross-Encoder scoring. Click citations to inspect source pages.</p>
          </div>
        </main>

        {viewerOpen && (
          <DocumentViewer
            filename={viewerDoc || documents[0]}
            conversationId={activeId}
            targetPage={targetCitationPage}
            onClose={() => setViewerOpen(false)}
          />
        )}
      </div>
    </div>
  );
}

function MessageBubble({
  id,
  role,
  content,
  username,
  defaultDoc,
  onCitationClick,
  onCopy,
  copied,
  onRegenerate,
}) {
  const assistant = role === 'assistant';
  return (
    <article className={`message ${assistant ? 'assistant' : 'user'}`}>
      <div className={assistant ? 'assistant-avatar' : 'message-avatar'}>
        {assistant ? <Icon name="orbit" size={18} /> : username[0].toUpperCase()}
      </div>
      <div className="message-body">
        <div className="message-header">
          <div className="message-author">
            <span className="author-name">{assistant ? 'Orbit' : username}</span>
            {assistant && <span className="ai-tag">Intelligence</span>}
          </div>

          {assistant && (
            <div className="message-tooltips">
              <button
                type="button"
                className="action-pill"
                onClick={() => onCopy && onCopy(content, id)}
                title="Copy markdown to clipboard"
              >
                <Icon name={copied ? 'check' : 'copy'} size={12} />
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
              {onRegenerate && (
                <button
                  type="button"
                  className="action-pill"
                  onClick={onRegenerate}
                  title="Regenerate this reply"
                >
                  <Icon name="refresh" size={12} />
                  <span>Regenerate</span>
                </button>
              )}
            </div>
          )}
        </div>

        <div className="message-content">
          {assistant ? (
            <Markdown
              components={{
                a: ({ href, children }) => {
                  if (href && href.startsWith('#citation:')) {
                    const parts = href.replace('#citation:', '').split(':');
                    return (
                      <button
                        type="button"
                        className="citation-pill"
                        onClick={() => onCitationClick && onCitationClick(parts[0], parts[1])}
                        title={`View ${parts[0]} on Page ${parts[1]}`}
                      >
                        {children}
                      </button>
                    );
                  }
                  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
                },
              }}
            >
              {formatCitations(content, defaultDoc)}
            </Markdown>
          ) : (
            <p className="user-text">{content}</p>
          )}
        </div>
      </div>
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

  useEffect(() => {
    checkSession();
  }, []);

  if (checking) {
    return (
      <div className="startup">
        <Brand />
        <div className="loading-orbit-ring" />
        <p>Connecting to Orbit Core...</p>
      </div>
    );
  }

  if (startupError) {
    return (
      <div className="startup">
        <Brand />
        <div className="error" role="alert">
          {startupError}
        </div>
        <button className="primary" onClick={checkSession}>
          Reconnect
        </button>
      </div>
    );
  }

  return user ? (
    <Chat key={user.id} user={user} onSignOut={() => setUser(null)} />
  ) : (
    <Auth onSignIn={setUser} />
  );
}
