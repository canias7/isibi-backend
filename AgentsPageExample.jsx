import React, { useState, useEffect } from 'react';
import TestAgentModal from './components/TestAgentModal';

/**
 * Agents Page with Test Voice Agent Feature
 * 
 * Shows how to integrate the test agent button
 */

export default function AgentsPage({ token }) {
  const [agents, setAgents] = useState([]);
  const [testingAgent, setTestingAgent] = useState(null);

  // Load agents
  useEffect(() => {
    fetch('https://your-backend.onrender.com/api/agents', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
    .then(res => res.json())
    .then(data => setAgents(data.agents || []))
    .catch(err => console.error('Failed to load agents:', err));
  }, [token]);

  return (
    <div className="agents-page">
      <div className="page-header">
        <h1>My AI Agents</h1>
        <button className="create-btn">+ Create Agent</button>
      </div>

      <div className="agents-grid">
        {agents.map(agent => (
          <div key={agent.id} className="agent-card">
            <div className="agent-header">
              <h3>{agent.name}</h3>
              <span className="agent-voice">🎙️ {agent.voice || 'alloy'}</span>
            </div>

            <div className="agent-info">
              <p className="phone-number">
                {agent.phone_number || 'No phone number'}
              </p>
              <p className="prompt-preview">
                {agent.system_prompt?.substring(0, 120)}...
              </p>
            </div>

            <div className="agent-actions">
              {/* TEST VOICE AGENT BUTTON */}
              <button
                onClick={() => setTestingAgent(agent)}
                className="test-btn"
                title="Test this agent with voice"
              >
                🎤 Test Agent
              </button>

              <button className="edit-btn">
                ✏️ Edit
              </button>

              <button className="delete-btn">
                🗑️ Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Test Agent Modal */}
      {testingAgent && (
        <TestAgentModal
          agent={testingAgent}
          token={token}
          onClose={() => setTestingAgent(null)}
        />
      )}

      <style jsx>{`
        .agents-page {
          padding: 32px;
        }

        .page-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 32px;
        }

        .page-header h1 {
          margin: 0;
          font-size: 28px;
        }

        .create-btn {
          padding: 12px 24px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 8px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: transform 0.2s;
        }

        .create-btn:hover {
          transform: translateY(-2px);
        }

        .agents-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
          gap: 24px;
        }

        .agent-card {
          background: white;
          border-radius: 12px;
          padding: 24px;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
          transition: transform 0.2s;
        }

        .agent-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }

        .agent-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }

        .agent-header h3 {
          margin: 0;
          font-size: 20px;
          color: #1f2937;
        }

        .agent-voice {
          font-size: 14px;
          color: #6b7280;
        }

        .agent-info {
          margin-bottom: 20px;
        }

        .phone-number {
          font-size: 14px;
          color: #667eea;
          font-weight: 600;
          margin: 0 0 12px 0;
        }

        .prompt-preview {
          font-size: 13px;
          color: #6b7280;
          line-height: 1.5;
          margin: 0;
        }

        .agent-actions {
          display: flex;
          gap: 8px;
        }

        .test-btn {
          flex: 1;
          padding: 10px 16px;
          background: linear-gradient(135deg, #10b981 0%, #059669 100%);
          color: white;
          border: none;
          border-radius: 6px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }

        .test-btn:hover {
          transform: scale(1.05);
          box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
        }

        .edit-btn {
          padding: 10px 16px;
          background: #f3f4f6;
          color: #374151;
          border: none;
          border-radius: 6px;
          font-size: 14px;
          cursor: pointer;
          transition: background 0.2s;
        }

        .edit-btn:hover {
          background: #e5e7eb;
        }

        .delete-btn {
          padding: 10px 16px;
          background: #fee2e2;
          color: #dc2626;
          border: none;
          border-radius: 6px;
          font-size: 14px;
          cursor: pointer;
          transition: background 0.2s;
        }

        .delete-btn:hover {
          background: #fecaca;
        }
      `}</style>
    </div>
  );
}
