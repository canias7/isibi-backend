import React, { useState, useEffect } from 'react';

/**
 * Admin Dashboard
 * 
 * Comprehensive admin panel with:
 * - Overview statistics
 * - Revenue charts
 * - User management
 * - Activity logs
 * - Voice chat conversations
 */

export default function AdminDashboard({ token }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [activity, setActivity] = useState([]);
  const [voiceLogs, setVoiceLogs] = useState([]);
  const [revenueChart, setRevenueChart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedConversation, setSelectedConversation] = useState(null);

  // Load dashboard data
  useEffect(() => {
    loadDashboardStats();
    loadRecentActivity();
  }, []);

  // Load data based on active tab
  useEffect(() => {
    if (activeTab === 'users') {
      loadUsers();
    } else if (activeTab === 'voice-chats') {
      loadVoiceChats();
    } else if (activeTab === 'revenue') {
      loadRevenueChart();
    }
  }, [activeTab]);

  const loadDashboardStats = async () => {
    try {
      const res = await fetch('https://your-backend.onrender.com/api/admin/dashboard', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setStats(data);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load stats:', err);
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const res = await fetch('https://your-backend.onrender.com/api/admin/users', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setUsers(data.users || []);
    } catch (err) {
      console.error('Failed to load users:', err);
    }
  };

  const loadRecentActivity = async () => {
    try {
      const res = await fetch('https://your-backend.onrender.com/api/admin/activity', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setActivity(data.activity || []);
    } catch (err) {
      console.error('Failed to load activity:', err);
    }
  };

  const loadVoiceChats = async () => {
    try {
      const res = await fetch('https://your-backend.onrender.com/api/admin/voice-chat-logs', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setVoiceLogs(data.logs || []);
    } catch (err) {
      console.error('Failed to load voice chats:', err);
    }
  };

  const loadRevenueChart = async () => {
    try {
      const res = await fetch('https://your-backend.onrender.com/api/admin/revenue-chart?days=30', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      setRevenueChart(data);
    } catch (err) {
      console.error('Failed to load revenue chart:', err);
    }
  };

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="loader"></div>
        <p>Loading admin dashboard...</p>
      </div>
    );
  }

  return (
    <div className="admin-dashboard">
      {/* Header */}
      <div className="admin-header">
        <h1>🛠️ Admin Dashboard</h1>
        <p className="subtitle">Platform management and analytics</p>
      </div>

      {/* Tabs */}
      <div className="admin-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          📊 Overview
        </button>
        <button
          className={`tab ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          👥 Users
        </button>
        <button
          className={`tab ${activeTab === 'revenue' ? 'active' : ''}`}
          onClick={() => setActiveTab('revenue')}
        >
          💰 Revenue
        </button>
        <button
          className={`tab ${activeTab === 'voice-chats' ? 'active' : ''}`}
          onClick={() => setActiveTab('voice-chats')}
        >
          🎤 Voice Chats
        </button>
        <button
          className={`tab ${activeTab === 'activity' ? 'active' : ''}`}
          onClick={() => setActiveTab('activity')}
        >
          📝 Activity
        </button>
      </div>

      {/* Content */}
      <div className="admin-content">
        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && stats && (
          <div className="overview-tab">
            {/* Stats Grid */}
            <div className="stats-grid">
              {/* Users */}
              <div className="stat-card">
                <div className="stat-icon">👥</div>
                <div className="stat-content">
                  <h3>{stats.users.total}</h3>
                  <p>Total Users</p>
                  <span className="stat-detail">
                    +{stats.users.new_week} this week
                  </span>
                </div>
              </div>

              {/* Revenue */}
              <div className="stat-card">
                <div className="stat-icon">💰</div>
                <div className="stat-content">
                  <h3>${stats.revenue.total.toFixed(2)}</h3>
                  <p>Total Revenue</p>
                  <span className="stat-detail">
                    ${stats.revenue.month.toFixed(2)} this month
                  </span>
                </div>
              </div>

              {/* Calls */}
              <div className="stat-card">
                <div className="stat-icon">📞</div>
                <div className="stat-content">
                  <h3>{stats.calls.total}</h3>
                  <p>Total Calls</p>
                  <span className="stat-detail">
                    {stats.calls.week} this week
                  </span>
                </div>
              </div>

              {/* Agents */}
              <div className="stat-card">
                <div className="stat-icon">🤖</div>
                <div className="stat-content">
                  <h3>{stats.agents.total}</h3>
                  <p>Total Agents</p>
                  <span className="stat-detail">
                    {stats.agents.active_users} active users
                  </span>
                </div>
              </div>

              {/* Credits */}
              <div className="stat-card">
                <div className="stat-icon">🎫</div>
                <div className="stat-content">
                  <h3>${stats.credits.total_purchased.toFixed(2)}</h3>
                  <p>Credits Sold</p>
                  <span className="stat-detail">
                    ${stats.credits.total_used.toFixed(2)} used
                  </span>
                </div>
              </div>

              {/* Avg Call Duration */}
              <div className="stat-card">
                <div className="stat-icon">⏱️</div>
                <div className="stat-content">
                  <h3>{Math.floor(stats.calls.avg_duration / 60)}m {stats.calls.avg_duration % 60}s</h3>
                  <p>Avg Call Duration</p>
                  <span className="stat-detail">
                    Across all calls
                  </span>
                </div>
              </div>
            </div>

            {/* Recent Activity */}
            <div className="recent-activity-section">
              <h2>Recent Activity</h2>
              <div className="activity-list">
                {activity.slice(0, 10).map((item, idx) => (
                  <div key={idx} className={`activity-item ${item.type}`}>
                    <div className="activity-icon">
                      {item.type === 'call' && '📞'}
                      {item.type === 'purchase' && '💳'}
                      {item.type === 'signup' && '✨'}
                    </div>
                    <div className="activity-content">
                      <p className="activity-user">{item.user_email}</p>
                      <p className="activity-details">{item.details}</p>
                    </div>
                    <div className="activity-time">
                      {new Date(item.timestamp).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* USERS TAB */}
        {activeTab === 'users' && (
          <div className="users-tab">
            <h2>All Users</h2>
            <div className="users-table-container">
              <table className="users-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Email</th>
                    <th>Balance</th>
                    <th>Purchased</th>
                    <th>Used</th>
                    <th>Agents</th>
                    <th>Calls</th>
                    <th>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(user => (
                    <tr key={user.id}>
                      <td>{user.id}</td>
                      <td>{user.email}</td>
                      <td>${user.balance.toFixed(2)}</td>
                      <td>${user.total_purchased.toFixed(2)}</td>
                      <td>${user.total_used.toFixed(2)}</td>
                      <td>{user.agent_count}</td>
                      <td>{user.call_count}</td>
                      <td>{new Date(user.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* REVENUE TAB */}
        {activeTab === 'revenue' && revenueChart && (
          <div className="revenue-tab">
            <h2>Revenue Analytics</h2>
            <div className="chart-container">
              <div className="chart-placeholder">
                <p>📈 Revenue Chart (Last 30 Days)</p>
                <p className="chart-note">
                  Integrate with Chart.js or Recharts to display:
                </p>
                <pre>{JSON.stringify(revenueChart, null, 2)}</pre>
              </div>
            </div>
          </div>
        )}

        {/* VOICE CHATS TAB */}
        {activeTab === 'voice-chats' && (
          <div className="voice-chats-tab">
            <h2>Talk to ISIBI Conversations</h2>
            <div className="voice-chats-grid">
              {voiceLogs.map(log => (
                <div
                  key={log.id}
                  className="voice-chat-card"
                  onClick={() => setSelectedConversation(log)}
                >
                  <div className="voice-chat-header">
                    <span className="session-id">🎤 Session {log.session_id.substring(0, 8)}...</span>
                    <span className="turns-count">{log.total_turns} messages</span>
                  </div>
                  <div className="voice-chat-meta">
                    <span>IP: {log.client_ip}</span>
                    <span>{new Date(log.created_at).toLocaleString()}</span>
                  </div>
                  <button className="view-transcript-btn">View Transcript</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ACTIVITY TAB */}
        {activeTab === 'activity' && (
          <div className="activity-tab">
            <h2>Platform Activity</h2>
            <div className="activity-list-full">
              {activity.map((item, idx) => (
                <div key={idx} className={`activity-item-full ${item.type}`}>
                  <div className="activity-type-badge">
                    {item.type === 'call' && '📞 Call'}
                    {item.type === 'purchase' && '💳 Purchase'}
                    {item.type === 'signup' && '✨ Signup'}
                  </div>
                  <div className="activity-main">
                    <p className="activity-user-full">{item.user_email}</p>
                    <p className="activity-details-full">{item.details}</p>
                  </div>
                  <div className="activity-timestamp">
                    {new Date(item.timestamp).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Conversation Modal */}
      {selectedConversation && (
        <div className="conversation-modal-overlay" onClick={() => setSelectedConversation(null)}>
          <div className="conversation-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>🎤 Conversation Transcript</h3>
              <button onClick={() => setSelectedConversation(null)}>✕</button>
            </div>
            <div className="modal-content">
              <div className="conversation-meta">
                <p><strong>Session ID:</strong> {selectedConversation.session_id}</p>
                <p><strong>IP Address:</strong> {selectedConversation.client_ip}</p>
                <p><strong>Date:</strong> {new Date(selectedConversation.created_at).toLocaleString()}</p>
                <p><strong>Messages:</strong> {selectedConversation.total_turns}</p>
              </div>
              <div className="conversation-transcript">
                {selectedConversation.conversation.map((msg, idx) => (
                  <div key={idx} className={`transcript-message ${msg.role}`}>
                    <div className="message-header">
                      <strong>{msg.role === 'user' ? '👤 Customer' : '🤖 ISIBI'}</strong>
                      <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <div className="message-text">{msg.content}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .admin-dashboard {
          padding: 32px;
          max-width: 1400px;
          margin: 0 auto;
        }

        .admin-header {
          margin-bottom: 32px;
        }

        .admin-header h1 {
          margin: 0;
          font-size: 32px;
          color: #1f2937;
        }

        .subtitle {
          margin: 8px 0 0 0;
          color: #6b7280;
          font-size: 16px;
        }

        .admin-tabs {
          display: flex;
          gap: 8px;
          border-bottom: 2px solid #e5e7eb;
          margin-bottom: 32px;
        }

        .tab {
          padding: 12px 24px;
          background: none;
          border: none;
          border-bottom: 3px solid transparent;
          font-size: 15px;
          font-weight: 600;
          color: #6b7280;
          cursor: pointer;
          transition: all 0.2s;
        }

        .tab:hover {
          color: #667eea;
        }

        .tab.active {
          color: #667eea;
          border-bottom-color: #667eea;
        }

        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
          gap: 20px;
          margin-bottom: 40px;
        }

        .stat-card {
          background: white;
          border-radius: 12px;
          padding: 24px;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
          display: flex;
          gap: 16px;
          transition: transform 0.2s;
        }

        .stat-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
        }

        .stat-icon {
          font-size: 36px;
        }

        .stat-content h3 {
          margin: 0;
          font-size: 28px;
          color: #1f2937;
        }

        .stat-content p {
          margin: 4px 0;
          color: #6b7280;
          font-size: 14px;
        }

        .stat-detail {
          font-size: 12px;
          color: #10b981;
        }

        .recent-activity-section h2 {
          margin: 0 0 20px 0;
          font-size: 20px;
        }

        .activity-list {
          background: white;
          border-radius: 12px;
          padding: 16px;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
        }

        .activity-item {
          display: flex;
          gap: 12px;
          padding: 12px;
          border-bottom: 1px solid #e5e7eb;
          align-items: center;
        }

        .activity-item:last-child {
          border-bottom: none;
        }

        .activity-icon {
          font-size: 24px;
        }

        .activity-content {
          flex: 1;
        }

        .activity-user {
          margin: 0;
          font-weight: 600;
          font-size: 14px;
        }

        .activity-details {
          margin: 4px 0 0 0;
          font-size: 13px;
          color: #6b7280;
        }

        .activity-time {
          font-size: 12px;
          color: #9ca3af;
        }

        .users-table-container {
          background: white;
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
        }

        .users-table {
          width: 100%;
          border-collapse: collapse;
        }

        .users-table th {
          background: #f9fafb;
          padding: 12px 16px;
          text-align: left;
          font-weight: 600;
          font-size: 13px;
          color: #6b7280;
          text-transform: uppercase;
        }

        .users-table td {
          padding: 12px 16px;
          border-top: 1px solid #e5e7eb;
          font-size: 14px;
        }

        .users-table tr:hover {
          background: #f9fafb;
        }

        .voice-chats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 20px;
        }

        .voice-chat-card {
          background: white;
          border-radius: 12px;
          padding: 20px;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
          cursor: pointer;
          transition: transform 0.2s;
        }

        .voice-chat-card:hover {
          transform: translateY(-4px);
        }

        .voice-chat-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 12px;
        }

        .session-id {
          font-weight: 600;
          font-size: 14px;
        }

        .turns-count {
          background: #667eea;
          color: white;
          padding: 2px 8px;
          border-radius: 12px;
          font-size: 12px;
        }

        .voice-chat-meta {
          font-size: 12px;
          color: #6b7280;
          display: flex;
          justify-content: space-between;
          margin-bottom: 16px;
        }

        .view-transcript-btn {
          width: 100%;
          padding: 8px;
          background: #667eea;
          color: white;
          border: none;
          border-radius: 6px;
          font-weight: 600;
          cursor: pointer;
        }

        .conversation-modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 20px;
        }

        .conversation-modal {
          background: white;
          border-radius: 16px;
          max-width: 800px;
          width: 100%;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          padding: 24px;
          border-bottom: 1px solid #e5e7eb;
        }

        .modal-header h3 {
          margin: 0;
        }

        .modal-header button {
          background: none;
          border: none;
          font-size: 24px;
          cursor: pointer;
        }

        .modal-content {
          padding: 24px;
          overflow-y: auto;
        }

        .conversation-meta {
          background: #f9fafb;
          padding: 16px;
          border-radius: 8px;
          margin-bottom: 20px;
        }

        .conversation-meta p {
          margin: 8px 0;
          font-size: 14px;
        }

        .transcript-message {
          margin-bottom: 16px;
          padding: 12px;
          border-radius: 8px;
        }

        .transcript-message.user {
          background: #ede9fe;
          border-left: 4px solid #7c3aed;
        }

        .transcript-message.assistant {
          background: #dbeafe;
          border-left: 4px solid #3b82f6;
        }

        .message-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
          font-size: 13px;
        }

        .message-text {
          line-height: 1.5;
        }

        .admin-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 100px 20px;
        }

        .loader {
          width: 50px;
          height: 50px;
          border: 4px solid #e5e7eb;
          border-top-color: #667eea;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
