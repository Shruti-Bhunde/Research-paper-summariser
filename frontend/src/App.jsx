import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import './App.css';

const API_BASE_URL = 'http://localhost:8000/api';
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const AUTH_TOKEN_KEY = 'research_summariser_google_token';
const SELECTED_PAPER_KEY = 'research_summariser_selected_paper';

const LOADING_STEPS = [
  'Uploading PDF document...',
  'Extracting page structure and metadata...',
  'Gemini multimodal AI parsing document text...',
  'Analyzing charts, graphs, and visual figures...',
  'Compiling structured summary data...',
  'Building final PDF report...',
];

const CHAT_SUGGESTIONS = [
  'What is the main contribution of this paper?',
  'Can you explain the key limitation?',
  'Give me a simple summary I can present.',
  'What follow-up question should I ask the author?',
];

function BookIcon() {
  return (
    <svg className="upload-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function normalizePaperItem(paper) {
  if (!paper) return null;
  return {
    summary_id: paper.summary_id,
    title: paper.title || paper.summary?.title || paper.metadata?.title || 'Untitled Paper',
    created_at: paper.created_at,
    updated_at: paper.updated_at,
    author: paper.author || paper.metadata?.author || 'Unknown',
    page_count: paper.page_count ?? paper.metadata?.page_count ?? 0,
    original_filename: paper.original_filename || '',
    chat_turns: paper.chat_turns ?? (paper.conversation_history?.length || 0),
    summary_pdf_url: paper.summary_pdf_url,
    original_pdf_url: paper.original_pdf_url,
  };
}

function normalizePaperDetail(paper) {
  if (!paper) return null;
  return {
    ...normalizePaperItem(paper),
    summary: paper.summary || {},
    metadata: paper.metadata || {},
    conversation_history: paper.conversation_history || [],
    conversation_memory: paper.conversation_memory || '',
  };
}

function formatDateTime(value) {
  if (!value) return 'Unknown';
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function loadGoogleScript() {
  if (window.google?.accounts?.id) return;
  await new Promise((resolve, reject) => {
    const existingScript = document.querySelector('script[data-google-identity="true"]');
    if (existingScript) {
      existingScript.addEventListener('load', resolve, { once: true });
      existingScript.addEventListener('error', reject, { once: true });
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.dataset.googleIdentity = 'true';
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

export default function App() {
  const loginButtonRef = useRef(null);
  const chatEndRef = useRef(null);
  const authTokenRef = useRef('');
  const summaryPdfUrlRef = useRef('');
  const originalPdfUrlRef = useRef('');

  const [authLoading, setAuthLoading] = useState(true);
  const [authUser, setAuthUser] = useState(null);
  const [authToken, setAuthToken] = useState('');
  const [authError, setAuthError] = useState('');

  const [papers, setPapers] = useState([]);
  const [papersLoading, setPapersLoading] = useState(false);
  const [selectedPaperId, setSelectedPaperId] = useState('');
  const [selectedPaper, setSelectedPaper] = useState(null);
  const [paperMode, setPaperMode] = useState('summary');
  const [summaryTab, setSummaryTab] = useState('overall_summary');

  const [summaryPdfUrl, setSummaryPdfUrl] = useState('');
  const [originalPdfUrl, setOriginalPdfUrl] = useState('');
  const [viewerMode, setViewerMode] = useState('summary');

  const [file, setFile] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    authTokenRef.current = authToken;
  }, [authToken]);

  useEffect(() => {
    summaryPdfUrlRef.current = summaryPdfUrl;
    originalPdfUrlRef.current = originalPdfUrl;
  }, [summaryPdfUrl, originalPdfUrl]);

  const revokePreviewUrls = useCallback(() => {
    if (summaryPdfUrlRef.current) URL.revokeObjectURL(summaryPdfUrlRef.current);
    if (originalPdfUrlRef.current) URL.revokeObjectURL(originalPdfUrlRef.current);
  }, []);

  const selectPaper = useCallback(async (paperId, options = {}) => {
    const token = options.token || authTokenRef.current;
    if (!paperId || !token) return;

    setPapersLoading(true);
    try {
      const detailResponse = await axios.get(`${API_BASE_URL}/papers/${paperId}`, {
        headers: authHeaders(token),
      });
      const paper = normalizePaperDetail(detailResponse.data.paper);

      revokePreviewUrls();
      const [summaryBlob, originalBlob] = await Promise.all([
        axios.get(`${API_BASE_URL}${paper.summary_pdf_url}`, {
          responseType: 'blob',
          headers: authHeaders(token),
        }),
        axios.get(`${API_BASE_URL}${paper.original_pdf_url}`, {
          responseType: 'blob',
          headers: authHeaders(token),
        }),
      ]);

      const summaryObjectUrl = URL.createObjectURL(summaryBlob.data);
      const originalObjectUrl = URL.createObjectURL(originalBlob.data);

      setSelectedPaper(paper);
      setSelectedPaperId(paper.summary_id);
      localStorage.setItem(SELECTED_PAPER_KEY, paper.summary_id);
      setChatMessages(paper.conversation_history || []);
      setSummaryPdfUrl(summaryObjectUrl);
      setOriginalPdfUrl(originalObjectUrl);
      setViewerMode('summary');
      setPaperMode('chat');
      setPapers((current) => {
        const normalized = normalizePaperItem(paper);
        const filtered = current.filter((item) => item.summary_id !== normalized.summary_id);
        return [normalized, ...filtered].sort((left, right) => {
          const leftTime = new Date(left.updated_at || left.created_at || 0).getTime();
          const rightTime = new Date(right.updated_at || right.created_at || 0).getTime();
          return rightTime - leftTime;
        });
      });
    } catch (error) {
      const message = error.response?.data?.detail || 'Could not load this paper right now.';
      setAuthError(message);
    } finally {
      setPapersLoading(false);
    }
  }, [revokePreviewUrls]);

  const refreshPapers = useCallback(async (token = '') => {
    const resolvedToken = token || authTokenRef.current;
    if (!resolvedToken) return [];
    const response = await axios.get(`${API_BASE_URL}/papers`, {
      headers: authHeaders(resolvedToken),
    });
    const nextPapers = (response.data.papers || []).map(normalizePaperItem);
    setPapers(nextPapers);
    return nextPapers;
  }, []);

  const finalizeLogin = useCallback(async (credential) => {
    const response = await axios.post(`${API_BASE_URL}/auth/google`, { credential });
    setAuthToken(credential);
    setAuthUser(response.data.user);
    setAuthError('');
    localStorage.setItem(AUTH_TOKEN_KEY, credential);

    const nextPapers = (response.data.papers || []).map(normalizePaperItem);
    setPapers(nextPapers);

    const storedPaperId = localStorage.getItem(SELECTED_PAPER_KEY);
    const paperIdToOpen = storedPaperId || nextPapers[0]?.summary_id || '';
    if (paperIdToOpen) {
      await selectPaper(paperIdToOpen, { token: credential });
    } else {
      revokePreviewUrls();
      setSelectedPaper(null);
      setSelectedPaperId('');
      setChatMessages([]);
    }
  }, [selectPaper, revokePreviewUrls]);

  const signOut = () => {
    revokePreviewUrls();
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(SELECTED_PAPER_KEY);
    setAuthUser(null);
    setAuthToken('');
    setPapers([]);
    setSelectedPaper(null);
    setSelectedPaperId('');
    setChatMessages([]);
    setChatInput('');
    setFile(null);
    setUploadError('');
    setAuthError('');
    setSummaryPdfUrl('');
    setOriginalPdfUrl('');
    setViewerMode('summary');
    setPaperMode('summary');
    setSummaryTab('overall_summary');
  };

  const deletePaper = async (summaryId, e) => {
    e.stopPropagation();
    const token = authTokenRef.current;
    try {
      await axios.delete(`${API_BASE_URL}/papers/${summaryId}`, {
        headers: authHeaders(token),
      });
      setPapers((prev) => prev.filter((p) => p.summary_id !== summaryId));
      if (selectedPaperId === summaryId) {
        clearState();
      }
    } catch (err) {
      console.error('Failed to delete paper:', err);
    }
  };

  useEffect(() => {
    let mounted = true;

    const restoreSession = async () => {
      const storedToken = localStorage.getItem(AUTH_TOKEN_KEY);
      if (!storedToken) {
        if (mounted) setAuthLoading(false);
        return;
      }

      setAuthToken(storedToken);

      try {
        const response = await axios.get(`${API_BASE_URL}/me`, {
          headers: authHeaders(storedToken),
        });

        if (!mounted) return;

        setAuthUser(response.data.user);
        const nextPapers = (response.data.papers || []).map(normalizePaperItem);
        setPapers(nextPapers);

        const storedPaperId = localStorage.getItem(SELECTED_PAPER_KEY);
        const paperIdToOpen = storedPaperId || nextPapers[0]?.summary_id || '';
        if (paperIdToOpen) {
          await selectPaper(paperIdToOpen, { token: storedToken });
          setPaperMode('chat');
        }
      } catch (error) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        localStorage.removeItem(SELECTED_PAPER_KEY);
        setAuthError(error.response?.data?.detail || 'Google session expired. Please sign in again.');
      } finally {
        if (mounted) setAuthLoading(false);
      }
    };

    restoreSession();

    return () => {
      mounted = false;
      revokePreviewUrls();
    };
  }, [revokePreviewUrls, selectPaper]);

  useEffect(() => {
    let cancelled = false;

    const renderGoogleButton = async () => {
      if (authUser || authLoading) return;
      if (!GOOGLE_CLIENT_ID) {
        setAuthError('Set VITE_GOOGLE_CLIENT_ID in the frontend environment to enable Google login.');
        return;
      }

      await loadGoogleScript();
      if (cancelled || !loginButtonRef.current || !window.google?.accounts?.id) return;

      loginButtonRef.current.innerHTML = '';
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (response) => {
          try {
            setAuthError('');
            await finalizeLogin(response.credential);
          } catch (error) {
            setAuthError(error.response?.data?.detail || 'Google login failed. Please try again.');
          }
        },
      });
      window.google.accounts.id.renderButton(loginButtonRef.current, {
        theme: 'outline',
        size: 'large',
        width: 320,
        text: 'signin_with',
      });
    };

    renderGoogleButton();

    return () => {
      cancelled = true;
    };
  }, [authLoading, authUser, finalizeLogin]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatLoading]);

  useEffect(() => {
    let interval;
    if (uploadLoading) {
      interval = setInterval(() => {
        setLoadingStep((previous) => (previous < LOADING_STEPS.length - 1 ? previous + 1 : previous));
      }, 7000);
    } else {
      setLoadingStep(0);
    }
    return () => clearInterval(interval);
  }, [uploadLoading]);

  const validateAndSetFile = (selectedFile) => {
    setUploadError('');
    if (!selectedFile) return;
    if (selectedFile.type !== 'application/pdf' && !selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Please upload a PDF document.');
      return;
    }
    const maxSize = 20 * 1024 * 1024;
    if (selectedFile.size > maxSize) {
      setUploadError('File is too large. The maximum size is 20 MB.');
      return;
    }
    setFile(selectedFile);
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragging(false);
    if (event.dataTransfer.files?.[0]) {
      validateAndSetFile(event.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (event) => {
    if (event.target.files?.[0]) {
      validateAndSetFile(event.target.files[0]);
    }
  };

  const generateSummary = async () => {
    const token = authTokenRef.current;
    if (!file || !token) return;

    setUploadLoading(true);
    setUploadError('');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API_BASE_URL}/summarize`, formData, {
        headers: {
          ...authHeaders(token),
          'Content-Type': 'multipart/form-data',
        },
      });

      const paper = normalizePaperDetail(response.data.paper);
      const nextPapers = await refreshPapers(token);
      await selectPaper(paper.summary_id, { token });
      setPaperMode('summary');
      setSummaryTab('overall_summary');

      setPapers((current) => {
        const filtered = current.filter((item) => item.summary_id !== paper.summary_id);
        return [normalizePaperItem(paper), ...filtered].sort((left, right) => {
          const leftTime = new Date(left.updated_at || left.created_at || 0).getTime();
          const rightTime = new Date(right.updated_at || right.created_at || 0).getTime();
          return rightTime - leftTime;
        });
      });

      if (nextPapers.length > 0 && !selectedPaperId) {
        localStorage.setItem(SELECTED_PAPER_KEY, paper.summary_id);
      }

      setFile(null);
    } catch (error) {
      setUploadError(error.response?.data?.detail || 'We could not analyze that PDF right now.');
    } finally {
      setUploadLoading(false);
    }
  };

  const sendChatMessage = async (messageText = chatInput) => {
    const trimmed = messageText.trim();
    if (!trimmed || !selectedPaperId || chatLoading) return;

    const token = authTokenRef.current;

    setChatLoading(true);
    setChatInput('');

    try {
      const response = await axios.post(
        `${API_BASE_URL}/chat`,
        {
          summary_id: selectedPaperId,
          message: trimmed,
        },
        {
          headers: authHeaders(token),
        },
      );

      const paper = normalizePaperDetail(response.data.paper);
      setSelectedPaper(paper);
      setChatMessages(paper.conversation_history || []);
      setPaperMode('chat');
      setPapers((current) => {
        const next = normalizePaperItem(paper);
        const filtered = current.filter((item) => item.summary_id !== next.summary_id);
        return [next, ...filtered].sort((left, right) => {
          const leftTime = new Date(left.updated_at || left.created_at || 0).getTime();
          const rightTime = new Date(right.updated_at || right.created_at || 0).getTime();
          return rightTime - leftTime;
        });
      });
    } catch (error) {
      setChatMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: error.response?.data?.detail || 'I could not generate a reply right now. Please try again.',
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const openOriginalPdf = () => {
    if (!originalPdfUrl) return;
    window.open(originalPdfUrl, '_blank', 'noopener,noreferrer');
  };

  const downloadSummaryPdf = () => {
    if (!summaryPdfUrl || !selectedPaper) return;
    const link = document.createElement('a');
    link.href = summaryPdfUrl;
    link.download = `${selectedPaper.title || 'summary'}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const currentPdfUrl = viewerMode === 'original' ? originalPdfUrl : summaryPdfUrl;
  const summarySections = [
    { key: 'overall_summary', label: '1. Overall Summary' },
    { key: 'main_idea', label: '2. Main Idea' },
    { key: 'problem_solved', label: '3. Problem Solved' },
    { key: 'assumptions', label: '4. Assumptions' },
    { key: 'limitations', label: '5. Limitations' },
    { key: 'results_conclusion', label: '6. Conclusion' },
    { key: 'real_world_impact', label: '7. Impact' },
    { key: 'graphs_figures', label: '8. Figures' },
  ];

  if (authLoading) {
    return (
      <div className="auth-loading-screen">
        <div className="loading-container">
          <div className="loading-spinner-wrapper">
            <div className="loader-circle" />
            <div className="loader-glow" />
            <div className="loading-progress">…</div>
          </div>
          <div className="loading-text">
            <h3>Preparing your workspace</h3>
            <p>We’re loading your Google profile and saved papers.</p>
          </div>
        </div>
      </div>
    );
  }

  if (!authUser) {
    return (
      <div className="auth-screen">
        <div className="auth-card glass-panel">
          <div className="auth-hero">
            <p className="auth-eyebrow">Research Paper Summarizer AI</p>
            <h1>Sign in with Google</h1>
            <p>
              Your papers, summaries, summary PDFs, original PDFs, and chat history stay organized in one personal workspace.
            </p>
          </div>

          {authError && (
            <div className="error-banner" style={{ marginBottom: '1.25rem' }}>
              <span>{authError}</span>
            </div>
          )}

          <div className="auth-actions">
            <div ref={loginButtonRef} className="google-login-slot" />
          </div>

          <div className="auth-note">
            Google login is the only sign-in flow. No manual account creation.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-user-card">
          <img className="sidebar-avatar" src={authUser.picture || 'https://www.gravatar.com/avatar/?d=mp'} alt={authUser.name || authUser.email} />
          <div>
            <div className="sidebar-user-name">{authUser.name || 'Google User'}</div>
            <div className="sidebar-user-email">{authUser.email}</div>
          </div>
        </div>

        <button className="btn btn-secondary sidebar-logout" onClick={signOut}>
          Sign out
        </button>

        <div className="sidebar-section">
          <div className="sidebar-section-header">
            <h3>My Paper</h3>
            <span className="sidebar-count">{papers.length}</span>
          </div>

          {papers.length === 0 ? (
            <div className="empty-sidebar-state">
              Your previous papers will appear here after you summarize them.
            </div>
          ) : (
            <div className="paper-list">
              {papers.map((paper) => (
                <div key={paper.summary_id} className="paper-list-item-wrapper">
                  <button
                    className={`paper-list-item ${selectedPaperId === paper.summary_id ? 'active' : ''}`}
                    onClick={() => selectPaper(paper.summary_id)}
                    disabled={papersLoading}
                  >
                    <div className="paper-list-title">{paper.title}</div>
                    <div className="paper-list-meta">
                      <span>{paper.page_count} pages</span>
                      {paper.chat_turns > 0 && <span>{paper.chat_turns} messages</span>}
                    </div>
                    <div className="paper-list-date">{formatDateTime(paper.updated_at || paper.created_at)}</div>
                  </button>
                  <button
                    className="paper-delete-btn"
                    title="Delete this paper"
                    onClick={(e) => deletePaper(paper.summary_id, e)}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      <path d="M10 11v6" />
                      <path d="M14 11v6" />
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <h1>Personal Paper Workspace</h1>
            <p>Summaries, original PDFs, and conversation memory in one place.</p>
          </div>
          <button className="btn btn-primary" onClick={() => document.getElementById('pdf-file-input').click()}>
            Upload Paper
          </button>
        </header>

        <section className="upload-card glass-panel">
          {uploadError && (
            <div className="error-banner upload-error">
              <span>{uploadError}</span>
            </div>
          )}

          {!uploadLoading ? (
            <div
              className={`dropzone ${isDragging ? 'active' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => document.getElementById('pdf-file-input').click()}
            >
              <input
                id="pdf-file-input"
                type="file"
                accept=".pdf"
                style={{ display: 'none' }}
                onChange={handleFileChange}
              />
              <div className="dropzone-content">
                <div className="upload-icon-wrapper">
                  <BookIcon />
                </div>
                <div className="dropzone-prompt">
                  <h3>{file ? file.name : 'Drag & drop a research paper PDF'}</h3>
                  <p>{file ? `${(file.size / (1024 * 1024)).toFixed(2)} MB - ready to analyze` : 'or click to browse your device'}</p>
                </div>
                <div className="dropzone-constraints">PDF only, max 20 MB</div>
              </div>
            </div>
          ) : (
            <div className="loading-container compact">
              <div className="loading-spinner-wrapper">
                <div className="loader-circle" />
                <div className="loader-glow" />
                <div className="loading-progress">{Math.round(((loadingStep + 1) / LOADING_STEPS.length) * 100)}%</div>
              </div>
              <div className="loading-text">
                <h3>Analyzing your paper</h3>
                <p>{LOADING_STEPS[loadingStep]}</p>
              </div>
            </div>
          )}

          {file && !uploadLoading && (
            <div className="upload-actions">
              <button className="btn btn-primary" onClick={generateSummary}>
                Summarize and save
              </button>
              <button className="btn btn-secondary" onClick={() => setFile(null)}>
                Clear file
              </button>
            </div>
          )}
        </section>

        {selectedPaper && (
          <div className="workspace-header glass-panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', padding: '1.5rem 2rem' }}>
            <div className="paper-info">
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>{selectedPaper.title}</h2>
              <div className="paper-metadata" style={{ display: 'flex', gap: '1rem', marginTop: '0.4rem' }}>
                {selectedPaper.author && selectedPaper.author !== 'Unknown' && (
                  <span className="meta-badge">Author: <strong>{selectedPaper.author}</strong></span>
                )}
                <span className="meta-badge">Pages: <strong>{selectedPaper.page_count}</strong></span>
              </div>
            </div>
            <div className="workspace-mode-toggle" style={{ display: 'flex', gap: '0.5rem', background: 'rgba(255,255,255,0.03)', padding: '0.3rem', borderRadius: '12px', border: '1px solid var(--border-light)' }}>
              <button
                className={`btn ${paperMode === 'summary' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '0.5rem 1.2rem', borderRadius: '8px', fontSize: '0.9rem' }}
                onClick={() => setPaperMode('summary')}
              >
                Report
              </button>
              <button
                className={`btn ${paperMode === 'chat' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '0.5rem 1.2rem', borderRadius: '8px', fontSize: '0.9rem' }}
                onClick={() => setPaperMode('chat')}
              >
                Chat
              </button>
            </div>
          </div>
        )}

        {selectedPaper && paperMode === 'summary' ? (
          <section className="paper-workspace">
            <div className="glass-panel summary-result-panel">
              <div className="results-header-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '1rem' }}>
                <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.4rem', fontWeight: 700 }}>Paper Summary Details</h3>
                <button className="btn btn-primary" onClick={downloadSummaryPdf}>
                  <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" style={{ marginRight: '0.4rem' }}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-1m-4-4-4 4m0 0-4-4m4 4V4" />
                  </svg>
                  Download Summary PDF
                </button>
              </div>

              <div className="summary-viewport summary-result-viewport">
                <div className="summary-tab-bar">
                  {summarySections.map((section) => (
                    <button
                      key={section.key}
                      className={`summary-tab-btn ${summaryTab === section.key ? 'active' : ''}`}
                      onClick={() => setSummaryTab(section.key)}
                    >
                      {section.label}
                    </button>
                  ))}
                </div>

                <div className="viewport-body" style={{ marginTop: '1.5rem' }}>
                  {summaryTab === 'overall_summary' && <p>{selectedPaper.summary?.overall_summary || 'No content generated for this section.'}</p>}
                  {summaryTab === 'main_idea' && <p>{selectedPaper.summary?.main_idea || 'No content generated for this section.'}</p>}
                  {summaryTab === 'problem_solved' && <p>{selectedPaper.summary?.problem_solved || 'No content generated for this section.'}</p>}

                  {summaryTab === 'assumptions' && (
                    <div className="card-grid">
                      {selectedPaper.summary?.assumptions?.length > 0 ? (
                        selectedPaper.summary.assumptions.map((item, index) => (
                          <div key={index} className="info-card">
                            <div className="card-bullet-num">{index + 1}</div>
                            <div className="card-text">{item}</div>
                          </div>
                        ))
                      ) : (
                        <p>No assumptions were explicitly found in this study.</p>
                      )}
                    </div>
                  )}

                  {summaryTab === 'limitations' && (
                    <div className="card-grid">
                      {selectedPaper.summary?.limitations?.length > 0 ? (
                        selectedPaper.summary.limitations.map((item, index) => (
                          <div key={index} className="info-card limitation-card">
                            <div className="card-bullet-num">{index + 1}</div>
                            <div className="card-text">{item}</div>
                          </div>
                        ))
                      ) : (
                        <p>No limitations were explicitly found or reported.</p>
                      )}
                    </div>
                  )}

                  {summaryTab === 'results_conclusion' && <p>{selectedPaper.summary?.results_conclusion || 'No content generated for this section.'}</p>}
                  {summaryTab === 'real_world_impact' && <p>{selectedPaper.summary?.real_world_impact || 'No content generated for this section.'}</p>}

                  {summaryTab === 'graphs_figures' && (
                    <div className="figures-grid">
                      {selectedPaper.summary?.graphs_figures?.length > 0 ? (
                        selectedPaper.summary.graphs_figures.map((fig, index) => (
                          <div key={index} className="figure-card">
                            <div className="figure-card-header">
                              <div className="figure-icon-box">
                                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2zm0 0V9a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v10m-6 0a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2m0 0V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v14a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2z" />
                                </svg>
                              </div>
                              <h4>{fig.title || `Figure ${index + 1}`}</h4>
                            </div>
                            <p className="figure-explanation">{fig.explanation}</p>
                          </div>
                        ))
                      ) : (
                        <p>No visual figures or charts were identified or analyzed in this document.</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>
        ) : selectedPaper ? (
          <section className="paper-workspace">
            <div className="paper-grid">
              <div className="paper-panel pdf-panel glass-panel">
                <div className="paper-panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <p className="paper-kicker">PDF Viewer</p>
                  </div>
                  <div className="paper-panel-actions" style={{ display: 'flex', gap: '0.4rem' }}>
                    <button
                      className={`btn btn-secondary tab-button ${viewerMode === 'summary' ? 'active' : ''}`}
                      style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
                      onClick={() => setViewerMode('summary')}
                    >
                      Summary PDF
                    </button>
                    <button
                      className={`btn btn-secondary tab-button ${viewerMode === 'original' ? 'active' : ''}`}
                      style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
                      onClick={() => setViewerMode('original')}
                    >
                      Uploaded PDF
                    </button>
                  </div>
                </div>

                <div className="pdf-frame-wrap">
                  {currentPdfUrl ? (
                    <iframe title="PDF viewer" src={currentPdfUrl} className="pdf-frame" />
                  ) : (
                    <div className="pdf-empty-state">Loading PDF preview…</div>
                  )}
                </div>
              </div>

              <div className="paper-panel chat-panel glass-panel">
                <div className="chat-panel-header">
                  <div>
                    <p className="chat-kicker">Chat with uploaded PDF</p>
                  </div>
                  <span className="chat-status-pill">RAG + memory</span>
                </div>

                <div className="chat-messages">
                  {chatMessages.length === 0 ? (
                    <div className="chat-empty-state">
                      Ask a question about the paper to start the conversation.
                    </div>
                  ) : (
                    chatMessages.map((message, index) => (
                      <div key={`${message.role}-${index}`} className={`chat-message ${message.role}`}>
                        <div className="chat-message-label">{message.role === 'user' ? 'You' : 'Chatbot'}</div>
                        <div className="chat-message-bubble">{message.content}</div>
                        {message.role === 'assistant' && Array.isArray(message.sources) && message.sources.length > 0 && (
                          <div className="chat-sources">
                            <div className="chat-sources-label">Grounded on</div>
                            <div className="chat-source-chips">
                              {message.sources.map((source) => (
                                <span key={`${source.chunk_id}-${source.page}`} className="chat-source-chip">
                                  Chunk {source.chunk_id + 1} · Page {source.page}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  {chatLoading && (
                    <div className="chat-message assistant">
                      <div className="chat-message-label">Chatbot</div>
                      <div className="chat-message-bubble typing">Thinking through the paper…</div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                <div className="chat-suggestions">
                  {CHAT_SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      className="chat-suggestion"
                      onClick={() => sendChatMessage(suggestion)}
                      disabled={chatLoading}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>

                <form
                  className="chat-input-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    sendChatMessage();
                  }}
                >
                  <input
                    className="chat-input"
                    type="text"
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    placeholder="Ask anything about this paper..."
                    disabled={chatLoading}
                  />
                  <button className="btn btn-primary chat-send-btn" type="submit" disabled={chatLoading || !chatInput.trim()}>
                    {chatLoading ? 'Replying…' : 'Send'}
                  </button>
                </form>
              </div>
            </div>
          </section>
        ) : (
          <section className="empty-workspace glass-panel">
            <h2>No paper selected yet</h2>
            <p>Upload a new paper or choose one from “My Paper” to open the summary and chat.</p>
          </section>
        )}
      </main>
    </div>
  );
}
