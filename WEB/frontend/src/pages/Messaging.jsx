import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  MessageSquare, Send, Plus, ChevronLeft, X, Users, Search, Hash,
  Heart, MessageCircle, Repeat2, MoreHorizontal, Smile, Image, Paperclip,
  Globe, Lock, UserPlus, UserMinus, Settings, Check, CheckCheck, Loader2,
  Bell, BellOff, Pin, Archive, Trash2, Edit3, Flag, Eye, Share2,
  AlertCircle, Star, Shield, Clock, ArrowLeft, AtSign, TrendingUp,
} from 'lucide-react';
import BackButton from '../components/BackButton';

/* ═══════════════════════════════════════════════
   MAIN MESSAGING COMPONENT
   ═══════════════════════════════════════════════ */

export default function Messaging() {
  const [view, setView] = useState('hub'); // hub | conversations | chat | feed | post
  const [conversations, setConversations] = useState([]);
  const [posts, setPosts] = useState([]);
  const [selectedConv, setSelectedConv] = useState(null);
  const [selectedPost, setSelectedPost] = useState(null);
  const [loading, setLoading] = useState(false);
  const [convFilter, setConvFilter] = useState('all');
  const [feedTopic, setFeedTopic] = useState('');
  const [showCreate, setShowCreate] = useState(false);  // 'conv' | 'post' | false
  const { user } = useAuth();

  useEffect(() => {
    if (view === 'conversations') loadConversations();
    if (view === 'feed') loadFeed();
  }, [view, convFilter, feedTopic]);

  const loadConversations = async () => {
    setLoading(true);
    try {
      const params = {};
      if (convFilter !== 'all') params.conversation_type = convFilter;
      const { data } = await api.get('/messaging/conversations', { params });
      setConversations(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const loadFeed = async () => {
    setLoading(true);
    try {
      const params = {};
      if (feedTopic) params.topic = feedTopic;
      const { data } = await api.get('/messaging/feed', { params });
      setPosts(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  // Hub
  if (view === 'hub') {
    return (
      <div className="page-container" style={{ maxWidth: 700, margin: '0 auto' }}>
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1 style={{ fontSize: '1.8rem', margin: 0 }}>
              <MessageSquare size={28} style={{ marginRight: 8, verticalAlign: 'middle' }} />
              Messaging
            </h1>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <HubCard icon={<MessageSquare size={32} />} title="Direct Messages"
            desc="Private 1-on-1 conversations with peers or clinicians"
            onClick={() => { setConvFilter('direct'); setView('conversations'); }} />
          <HubCard icon={<Users size={32} />} title="Clinical Channels"
            desc="Communicate with your care team — physicians, nurses, social workers"
            onClick={() => { setConvFilter('clinical'); setView('conversations'); }} />
          <HubCard icon={<MessageCircle size={32} />} title="Group Chats"
            desc="Group conversations and care team channels"
            onClick={() => { setConvFilter('group'); setView('conversations'); }} />
          <HubCard icon={<Globe size={32} />} title="Community Feed"
            desc="Public timeline — share, discuss, and support each other"
            onClick={() => setView('feed')} />
        </div>
        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={() => { setConvFilter('all'); setView('conversations'); }}>
            All Conversations
          </button>
          <button className="btn btn-secondary" onClick={() => setView('feed')}>
            Browse Feed
          </button>
        </div>
      </div>
    );
  }

  // Conversations list
  if (view === 'conversations') {
    return (
      <div className="page-container">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button className="btn btn-secondary btn-sm" onClick={() => setView('hub')}>
            <ArrowLeft size={16} /> Back
          </button>
          <h2 style={{ flex: 1, margin: 0 }}>
            {convFilter === 'all' ? 'All Conversations' :
             convFilter === 'direct' ? 'Direct Messages' :
             convFilter === 'clinical' ? 'Clinical Channels' :
             convFilter === 'group' ? 'Group Chats' : 'Care Team'}
          </h2>
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate('conv')}>
            <Plus size={16} /> New
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {['all','direct','clinical','group','care_team'].map(f => (
            <button key={f} className={`btn btn-sm ${convFilter === f ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setConvFilter(f)}>
              {f === 'all' ? 'All' : f === 'care_team' ? 'Care Team' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        {loading ? <div className="text-center"><Loader2 size={24} className="spin" /></div> :
         conversations.length === 0 ? (
          <div className="text-center" style={{ padding: 40, color: '#888' }}>
            <MessageSquare size={48} style={{ opacity: 0.3 }} />
            <p>No conversations yet</p>
            <button className="btn btn-primary" onClick={() => setShowCreate('conv')}>
              Start a Conversation
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {conversations.map(c => (
              <ConversationRow key={c.id} conv={c} onClick={() => { setSelectedConv(c); setView('chat'); }} />
            ))}
          </div>
        )}

        {showCreate === 'conv' && (
          <CreateConversationModal
            defaultType={convFilter !== 'all' ? convFilter : 'direct'}
            onClose={() => setShowCreate(false)}
            onCreated={(c) => { setShowCreate(false); setSelectedConv(c); setView('chat'); }}
          />
        )}
      </div>
    );
  }

  // Chat view
  if (view === 'chat' && selectedConv) {
    return (
      <ChatView
        conv={selectedConv}
        onBack={() => { setView('conversations'); loadConversations(); }}
        userId={user?.id}
      />
    );
  }

  // Feed
  if (view === 'feed') {
    return (
      <div className="page-container">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <button className="btn btn-secondary btn-sm" onClick={() => setView('hub')}>
            <ArrowLeft size={16} /> Back
          </button>
          <h2 style={{ flex: 1, margin: 0 }}>Community Feed</h2>
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate('post')}>
            <Plus size={16} /> Post
          </button>
        </div>

        <FeedTopicBar topic={feedTopic} onChange={setFeedTopic} />

        {loading ? <div className="text-center"><Loader2 size={24} className="spin" /></div> :
         posts.length === 0 ? (
          <div className="text-center" style={{ padding: 40, color: '#888' }}>
            <Globe size={48} style={{ opacity: 0.3 }} />
            <p>No posts yet. Be the first to share!</p>
            <button className="btn btn-primary" onClick={() => setShowCreate('post')}>
              Create Post
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {posts.map(p => (
              <PostCard key={p.id} post={p} userId={user?.id}
                onSelect={() => { setSelectedPost(p); setView('post'); }}
                onRefresh={loadFeed}
              />
            ))}
          </div>
        )}

        {showCreate === 'post' && (
          <CreatePostModal
            onClose={() => setShowCreate(false)}
            onCreated={() => { setShowCreate(false); loadFeed(); }}
          />
        )}
      </div>
    );
  }

  // Post detail
  if (view === 'post' && selectedPost) {
    return (
      <PostDetailView
        postId={selectedPost.id}
        userId={user?.id}
        onBack={() => { setView('feed'); loadFeed(); }}
      />
    );
  }

  return null;
}

/* ── Hub Card ── */
function HubCard({ icon, title, desc, onClick }) {
  return (
    <div className="card" style={{ cursor: 'pointer', padding: 20, transition: 'transform 0.15s' }}
      onClick={onClick}
      onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
      onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
      <div style={{ color: 'var(--color-primary)', marginBottom: 8 }}>{icon}</div>
      <h3 style={{ margin: '0 0 4px' }}>{title}</h3>
      <p style={{ margin: 0, fontSize: '0.85rem', color: '#666' }}>{desc}</p>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   CONVERSATION ROW
   ═══════════════════════════════════════════════ */

function ConversationRow({ conv, onClick }) {
  const typeStyles = {
    direct: { bg: '#e3f2fd', color: '#1565c0', label: 'DM' },
    clinical: { bg: '#e8f5e9', color: '#2e7d32', label: 'Clinical' },
    group: { bg: '#f3e5f5', color: '#7b1fa2', label: 'Group' },
    care_team: { bg: '#fff3e0', color: '#e65100', label: 'Care Team' },
  };
  const style = typeStyles[conv.conversation_type] || typeStyles.direct;

  return (
    <div className="card" onClick={onClick}
      style={{ cursor: 'pointer', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{
        width: 40, height: 40, borderRadius: '50%', background: style.bg,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 700, color: style.color, fontSize: 14,
      }}>
        {conv.title ? conv.title[0].toUpperCase() : style.label[0]}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {conv.title || `${style.label} Conversation`}
          {conv.is_urgent && <span style={{ marginLeft: 6, color: '#d32f2f', fontSize: 12 }}>⚡ URGENT</span>}
        </div>
        <div style={{ fontSize: '0.8rem', color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {conv.last_message_preview || 'No messages yet'}
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        {conv.unread_count > 0 && (
          <span style={{
            background: 'var(--color-primary)', color: '#fff', borderRadius: 12,
            padding: '2px 8px', fontSize: 11, fontWeight: 700,
          }}>{conv.unread_count}</span>
        )}
        {conv.last_message_at && (
          <div style={{ fontSize: 11, color: '#aaa', marginTop: 4 }}>
            {new Date(conv.last_message_at).toLocaleDateString()}
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   CREATE CONVERSATION MODAL
   ═══════════════════════════════════════════════ */

function CreateConversationModal({ defaultType, onClose, onCreated }) {
  const [form, setForm] = useState({
    conversation_type: defaultType,
    title: '',
    description: '',
    specialty: '',
    priority: 'routine',
    is_urgent: false,
    member_ids: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        member_ids: form.member_ids ? form.member_ids.split(',').map(s => parseInt(s.trim())).filter(Boolean) : [],
      };
      const { data } = await api.post('/messaging/conversations', payload);
      onCreated(data);
    } catch (err) { console.error(err); }
    setSubmitting(false);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 500, width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>New Conversation</h3>
          <button className="btn btn-secondary btn-sm" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label className="form-label">Type</label>
            <select className="form-control" value={form.conversation_type}
              onChange={e => setForm({ ...form, conversation_type: e.target.value })}>
              <option value="direct">Direct Message</option>
              <option value="clinical">Clinical</option>
              <option value="group">Group Chat</option>
              <option value="care_team">Care Team</option>
            </select>
          </div>
          <div>
            <label className="form-label">Title</label>
            <input className="form-control" value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder={form.conversation_type === 'direct' ? 'Optional' : 'Channel name'} />
          </div>
          <div>
            <label className="form-label">Member IDs (comma-separated)</label>
            <input className="form-control" value={form.member_ids}
              onChange={e => setForm({ ...form, member_ids: e.target.value })}
              placeholder="e.g. 14, 15" />
          </div>
          {(form.conversation_type === 'clinical' || form.conversation_type === 'care_team') && (
            <>
              <div>
                <label className="form-label">Specialty</label>
                <input className="form-control" value={form.specialty}
                  onChange={e => setForm({ ...form, specialty: e.target.value })} placeholder="e.g. Cardiology" />
              </div>
              <div>
                <label className="form-label">Priority</label>
                <select className="form-control" value={form.priority}
                  onChange={e => setForm({ ...form, priority: e.target.value })}>
                  <option value="routine">Routine</option>
                  <option value="urgent">Urgent</option>
                  <option value="stat">Stat</option>
                </select>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={form.is_urgent}
                  onChange={e => setForm({ ...form, is_urgent: e.target.checked })} />
                Mark as urgent
              </label>
            </>
          )}
          <div>
            <label className="form-label">Description</label>
            <textarea className="form-control" rows={2} value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="Optional description..." />
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? <Loader2 size={16} className="spin" /> : 'Create'}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   CHAT VIEW (MESSAGES)
   ═══════════════════════════════════════════════ */

function ChatView({ conv, onBack, userId }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const messagesEnd = useRef(null);
  const wsRef = useRef(null);

  const loadMessages = useCallback(async () => {
    try {
      const { data } = await api.get(`/messaging/conversations/${conv.id}/messages`);
      setMessages(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [conv.id]);

  useEffect(() => {
    loadMessages();
    // Mark as read
    api.post(`/messaging/conversations/${conv.id}/read`).catch(() => {});

    // Connect WebSocket
    const token = localStorage.getItem('token');
    const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${location.host}/ws/messaging/${conv.id}?token=${token}`);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.type === 'message') {
        setMessages(prev => [...prev, {
          id: data.id,
          conversation_id: conv.id,
          sender_id: data.sender_id,
          message_type: data.message_type || 'text',
          content: data.content,
          file_url: data.file_url,
          file_name: data.file_name,
          is_edited: false,
          is_deleted: false,
          created_at: data.timestamp,
          read_receipts: [],
        }]);
      }
    };

    return () => { ws.close(); };
  }, [conv.id, loadMessages]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!text.trim()) return;
    setSending(true);
    try {
      // Try WebSocket first
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'message', content: text, message_type: 'text' }));
      } else {
        await api.post(`/messaging/conversations/${conv.id}/messages`, { content: text, message_type: 'text' });
        loadMessages();
      }
      setText('');
    } catch (e) { console.error(e); }
    setSending(false);
  };

  const typeLabels = { direct: 'Direct Message', clinical: 'Clinical', group: 'Group', care_team: 'Care Team' };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
        borderBottom: '1px solid #e0e0e0', background: '#fafafa',
      }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack}><ArrowLeft size={16} /></button>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700 }}>{conv.title || typeLabels[conv.conversation_type] || 'Chat'}</div>
          <div style={{ fontSize: 12, color: '#888' }}>
            {conv.members?.length || 0} members · {typeLabels[conv.conversation_type]}
            {conv.specialty && ` · ${conv.specialty}`}
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => setShowInfo(!showInfo)}>
          <Settings size={16} />
        </button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column' }}>
          {loading ? (
            <div className="text-center"><Loader2 size={24} className="spin" /></div>
          ) : messages.length === 0 ? (
            <div className="text-center" style={{ color: '#888', margin: 'auto' }}>
              <MessageSquare size={48} style={{ opacity: 0.3 }} />
              <p>No messages yet. Start the conversation!</p>
            </div>
          ) : (
            <>
              {messages.map(m => (
                <MessageBubble key={m.id} msg={m} isOwn={m.sender_id === userId} />
              ))}
              <div ref={messagesEnd} />
            </>
          )}
        </div>

        {/* Info panel */}
        {showInfo && (
          <div style={{ width: 260, borderLeft: '1px solid #e0e0e0', padding: 16, overflowY: 'auto' }}>
            <h4 style={{ marginTop: 0 }}>Details</h4>
            <p style={{ fontSize: 13, color: '#666' }}>{conv.description || 'No description'}</p>
            {conv.specialty && <p style={{ fontSize: 13 }}><strong>Specialty:</strong> {conv.specialty}</p>}
            {conv.priority && <p style={{ fontSize: 13 }}><strong>Priority:</strong> {conv.priority}</p>}
            <h4>Members ({conv.members?.length || 0})</h4>
            {(conv.members || []).map(m => (
              <div key={m.id} style={{ fontSize: 13, padding: '4px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Users size={14} />
                User #{m.user_id}
                <span style={{ fontSize: 11, color: '#888' }}>({m.role})</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{
        display: 'flex', padding: '8px 16px', gap: 8,
        borderTop: '1px solid #e0e0e0', background: '#fafafa',
      }}>
        <input
          className="form-control"
          style={{ flex: 1 }}
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
          placeholder="Type a message..."
          disabled={sending}
        />
        <button className="btn btn-primary" onClick={sendMessage} disabled={sending || !text.trim()}>
          {sending ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}

function MessageBubble({ msg, isOwn }) {
  if (msg.is_deleted) {
    return (
      <div style={{ textAlign: 'center', margin: '8px 0', fontSize: 12, color: '#aaa', fontStyle: 'italic' }}>
        Message deleted
      </div>
    );
  }
  if (msg.message_type === 'system') {
    return (
      <div style={{ textAlign: 'center', margin: '8px 0', fontSize: 12, color: '#888', fontStyle: 'italic' }}>
        {msg.content}
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex', justifyContent: isOwn ? 'flex-end' : 'flex-start',
      margin: '4px 0',
    }}>
      <div style={{
        maxWidth: '70%', padding: '8px 14px', borderRadius: 16,
        background: isOwn ? 'var(--color-primary)' : '#f0f0f0',
        color: isOwn ? '#fff' : '#333',
        borderTopRightRadius: isOwn ? 4 : 16,
        borderTopLeftRadius: isOwn ? 16 : 4,
      }}>
        {!isOwn && (
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 2, opacity: 0.7 }}>
            User #{msg.sender_id}
          </div>
        )}
        {msg.message_type === 'image' && msg.file_url && (
          <img src={msg.file_url} alt="" style={{ maxWidth: '100%', borderRadius: 8, marginBottom: 4 }} />
        )}
        {msg.message_type === 'file' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 13 }}>
            <Paperclip size={14} /> {msg.file_name || 'File'}
          </div>
        )}
        {msg.content && <div style={{ fontSize: 14, whiteSpace: 'pre-wrap' }}>{msg.content}</div>}
        <div style={{ fontSize: 10, opacity: 0.6, marginTop: 4, textAlign: 'right' }}>
          {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          {msg.is_edited && ' (edited)'}
          {msg.is_clinical && <span style={{ marginLeft: 4 }}>🏥</span>}
          {msg.is_priority && <span style={{ marginLeft: 4 }}>⚡</span>}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   COMMUNITY FEED
   ═══════════════════════════════════════════════ */

const TOPICS = ['', 'general', 'fitness', 'nutrition', 'mental-health', 'medications', 'lifestyle', 'community'];
const HEALTH_CATEGORIES = ['', 'fitness', 'nutrition', 'mood', 'mental_health', 'medications', 'labs', 'lifestyle', 'general'];

function FeedTopicBar({ topic, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
      {TOPICS.map(t => (
        <button key={t} className={`btn btn-sm ${topic === t ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => onChange(t)}>
          {t ? `#${t}` : 'All'}
        </button>
      ))}
    </div>
  );
}

function PostCard({ post, userId, onSelect, onRefresh }) {
  const [liking, setLiking] = useState(false);

  const toggleLike = async (e) => {
    e.stopPropagation();
    setLiking(true);
    try {
      if (post.user_liked) {
        await api.delete(`/messaging/feed/${post.id}/like`);
      } else {
        await api.post(`/messaging/feed/${post.id}/like?reaction=like`);
      }
      onRefresh();
    } catch (err) { console.error(err); }
    setLiking(false);
  };

  return (
    <div className="card" style={{ padding: 16, cursor: 'pointer' }} onClick={onSelect}>
      {/* Author header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 36, height: 36, borderRadius: '50%', background: '#e3f2fd',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, color: '#1565c0',
        }}>
          {post.is_anonymous ? '?' : `#${post.author_id}`}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>
            {post.is_anonymous ? 'Anonymous' : `User #${post.author_id}`}
          </div>
          <div style={{ fontSize: 11, color: '#888' }}>
            {new Date(post.created_at).toLocaleDateString()}
            {post.topic && <span style={{ marginLeft: 8 }}><Hash size={10} style={{ verticalAlign: 'middle' }} />{post.topic}</span>}
          </div>
        </div>
        {post.visibility !== 'public' && (
          <Lock size={14} style={{ color: '#888' }} title={post.visibility} />
        )}
        {post.is_pinned && <Pin size={14} style={{ color: '#f4a100' }} />}
      </div>

      {/* Content */}
      <p style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
        {post.content.length > 300 ? post.content.slice(0, 300) + '...' : post.content}
      </p>

      {/* Health badge */}
      {post.health_category && (
        <span style={{
          display: 'inline-block', background: '#e8f5e9', color: '#2e7d32',
          padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 600, marginBottom: 8,
        }}>
          {post.health_category.replace('_', ' ')}
        </span>
      )}

      {/* Hashtags */}
      {post.hashtags && (
        <div style={{ fontSize: 12, color: 'var(--color-primary)', marginBottom: 8 }}>
          {post.hashtags.split(',').map(t => `#${t.trim()}`).join(' ')}
        </div>
      )}

      {/* Engagement bar */}
      <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#666', borderTop: '1px solid #eee', paddingTop: 8 }}>
        <button onClick={toggleLike} disabled={liking}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', display: 'flex',
            alignItems: 'center', gap: 4, color: post.user_liked ? '#e53935' : '#666',
          }}>
          <Heart size={16} fill={post.user_liked ? '#e53935' : 'none'} /> {post.like_count}
        </button>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <MessageCircle size={16} /> {post.reply_count}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Repeat2 size={16} /> {post.repost_count}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Eye size={16} /> {post.view_count}
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   CREATE POST MODAL
   ═══════════════════════════════════════════════ */

function CreatePostModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    content: '',
    visibility: 'public',
    topic: '',
    hashtags: '',
    health_category: '',
    is_anonymous: false,
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.content.trim()) return;
    setSubmitting(true);
    try {
      const payload = { ...form };
      if (!payload.topic) delete payload.topic;
      if (!payload.hashtags) delete payload.hashtags;
      if (!payload.health_category) delete payload.health_category;
      await api.post('/messaging/feed', payload);
      onCreated();
    } catch (err) { console.error(err); }
    setSubmitting(false);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 550, width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>Create Post</h3>
          <button className="btn btn-secondary btn-sm" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <textarea
            className="form-control"
            rows={4}
            value={form.content}
            onChange={e => setForm({ ...form, content: e.target.value })}
            placeholder="What's on your mind? Share your health journey..."
            maxLength={5000}
            style={{ resize: 'vertical' }}
          />
          <div style={{ fontSize: 12, color: '#888', textAlign: 'right' }}>{form.content.length}/5000</div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <label className="form-label">Visibility</label>
              <select className="form-control" value={form.visibility}
                onChange={e => setForm({ ...form, visibility: e.target.value })}>
                <option value="public">🌍 Public</option>
                <option value="followers">👥 Followers</option>
                <option value="connections">🤝 Connections</option>
                <option value="private">🔒 Private</option>
              </select>
            </div>
            <div>
              <label className="form-label">Topic</label>
              <select className="form-control" value={form.topic}
                onChange={e => setForm({ ...form, topic: e.target.value })}>
                <option value="">— None —</option>
                {TOPICS.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="form-label">Health Category</label>
              <select className="form-control" value={form.health_category}
                onChange={e => setForm({ ...form, health_category: e.target.value })}>
                <option value="">— None —</option>
                {HEALTH_CATEGORIES.filter(Boolean).map(c => (
                  <option key={c} value={c}>{c.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">Hashtags</label>
              <input className="form-control" value={form.hashtags}
                onChange={e => setForm({ ...form, hashtags: e.target.value })}
                placeholder="e.g. wellness, fitness" />
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={form.is_anonymous}
              onChange={e => setForm({ ...form, is_anonymous: e.target.checked })} />
            Post anonymously
          </label>

          <button className="btn btn-primary" type="submit" disabled={submitting || !form.content.trim()}>
            {submitting ? <Loader2 size={16} className="spin" /> : 'Publish'}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   POST DETAIL VIEW
   ═══════════════════════════════════════════════ */

function PostDetailView({ postId, userId, onBack }) {
  const [post, setPost] = useState(null);
  const [replies, setReplies] = useState([]);
  const [replyText, setReplyText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    try {
      const [pRes, rRes] = await Promise.all([
        api.get(`/messaging/feed/${postId}`),
        api.get(`/messaging/feed/${postId}/replies`),
      ]);
      setPost(pRes.data);
      setReplies(rRes.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [postId]);

  useEffect(() => { load(); }, [load]);

  const sendReply = async () => {
    if (!replyText.trim()) return;
    setSending(true);
    try {
      await api.post(`/messaging/feed/${postId}/replies`, { content: replyText });
      setReplyText('');
      load();
    } catch (e) { console.error(e); }
    setSending(false);
  };

  const toggleLike = async () => {
    try {
      if (post.user_liked) {
        await api.delete(`/messaging/feed/${postId}/like`);
      } else {
        await api.post(`/messaging/feed/${postId}/like?reaction=like`);
      }
      load();
    } catch (e) { console.error(e); }
  };

  if (loading) return <div className="text-center" style={{ padding: 40 }}><Loader2 size={24} className="spin" /></div>;
  if (!post) return <div className="text-center" style={{ padding: 40 }}>Post not found</div>;

  return (
    <div className="page-container" style={{ maxWidth: 700, margin: '0 auto' }}>
      <button className="btn btn-secondary btn-sm" onClick={onBack} style={{ marginBottom: 16 }}>
        <ArrowLeft size={16} /> Back to Feed
      </button>

      {/* Post */}
      <div className="card" style={{ padding: 20, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <div style={{
            width: 40, height: 40, borderRadius: '50%', background: '#e3f2fd',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, color: '#1565c0',
          }}>
            {post.is_anonymous ? '?' : `#${post.author_id}`}
          </div>
          <div>
            <div style={{ fontWeight: 600 }}>{post.is_anonymous ? 'Anonymous' : `User #${post.author_id}`}</div>
            <div style={{ fontSize: 12, color: '#888' }}>
              {new Date(post.created_at).toLocaleString()}
              {post.topic && <span style={{ marginLeft: 8 }}><Hash size={10} style={{ verticalAlign: 'middle' }} />{post.topic}</span>}
              {post.is_edited && <span style={{ marginLeft: 8, fontStyle: 'italic' }}>(edited)</span>}
            </div>
          </div>
        </div>

        <div style={{ fontSize: 15, lineHeight: 1.6, whiteSpace: 'pre-wrap', marginBottom: 12 }}>
          {post.content}
        </div>

        {post.health_category && (
          <span style={{
            display: 'inline-block', background: '#e8f5e9', color: '#2e7d32',
            padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 600, marginBottom: 8,
          }}>
            {post.health_category.replace('_', ' ')}
          </span>
        )}
        {post.hashtags && (
          <div style={{ fontSize: 13, color: 'var(--color-primary)', marginBottom: 12 }}>
            {post.hashtags.split(',').map(t => `#${t.trim()}`).join(' ')}
          </div>
        )}

        {/* Engagement */}
        <div style={{ display: 'flex', gap: 20, fontSize: 14, borderTop: '1px solid #eee', paddingTop: 12 }}>
          <button onClick={toggleLike}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', display: 'flex',
              alignItems: 'center', gap: 4, color: post.user_liked ? '#e53935' : '#666',
            }}>
            <Heart size={18} fill={post.user_liked ? '#e53935' : 'none'} /> {post.like_count}
          </button>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#666' }}>
            <MessageCircle size={18} /> {post.reply_count}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#666' }}>
            <Eye size={18} /> {post.view_count}
          </span>
        </div>
      </div>

      {/* Reply input */}
      <div className="card" style={{ padding: 12, marginBottom: 16, display: 'flex', gap: 8 }}>
        <input
          className="form-control"
          style={{ flex: 1 }}
          value={replyText}
          onChange={e => setReplyText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); sendReply(); } }}
          placeholder="Write a reply..."
          disabled={sending}
        />
        <button className="btn btn-primary" onClick={sendReply} disabled={sending || !replyText.trim()}>
          {sending ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
        </button>
      </div>

      {/* Replies */}
      <h3>Replies ({replies.length})</h3>
      {replies.length === 0 ? (
        <p style={{ color: '#888', fontSize: 14 }}>No replies yet. Be the first to respond!</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {replies.map(r => (
            <div key={r.id} className="card" style={{ padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: '50%', background: '#f3e5f5',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 600, fontSize: 12, color: '#7b1fa2',
                }}>
                  #{r.author_id}
                </div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>User #{r.author_id}</div>
                <div style={{ fontSize: 11, color: '#888' }}>{new Date(r.created_at).toLocaleString()}</div>
                {r.is_edited && <span style={{ fontSize: 11, fontStyle: 'italic', color: '#888' }}>(edited)</span>}
              </div>
              <div style={{ fontSize: 14, whiteSpace: 'pre-wrap' }}>{r.content}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
