import React, { useState, useEffect, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';

/**
 * AI Help Assistant Widget
 * 
 * Floating chat widget that helps users with platform questions
 * Can be placed anywhere in the app
 */

export default function AskAIWidget({ token }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => uuidv4());
  const [commonQuestions, setCommonQuestions] = useState([]);
  const messagesEndRef = useRef(null);

  // Load common questions
  useEffect(() => {
    fetch('https://your-backend.onrender.com/api/help/common-questions')
      .then(res => res.json())
      .then(data => setCommonQuestions(data.questions || []))
      .catch(err => console.error('Failed to load common questions:', err));
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  // Initialize with welcome message when first opened
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages([{
        role: 'assistant',
        content: "Hi! I'm your AI assistant. I can help you with anything about using the ISIBI platform. What would you like to know?",
        timestamp: new Date()
      }]);
    }
  }, [isOpen]);

  const sendMessage = async (messageText = null) => {
    const userMessage = messageText || input.trim();
    if (!userMessage || loading) return;

    setInput('');
    setLoading(true);

    // Add user message to UI
    const newUserMessage = {
      role: 'user',
      content: userMessage,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, newUserMessage]);

    try {
      // Prepare conversation history
      const conversationHistory = messages.map(msg => ({
        role: msg.role,
        content: msg.content
      }));

      // Call API
      const response = await fetch('https://your-backend.onrender.com/api/help/ask', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userMessage,
          session_id: sessionId,
          conversation_history: conversationHistory
        })
      });

      const data = await response.json();

      if (data.success) {
        // Add AI response to UI
        const aiMessage = {
          role: 'assistant',
          content: data.response,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, aiMessage]);
      } else {
        throw new Error(data.error || 'Failed to get response');
      }
    } catch (error) {
      console.error('Help AI error:', error);
      
      // Add error message
      const errorMessage = {
        role: 'assistant',
        content: "Sorry, I'm having trouble right now. Please try again or contact support.",
        timestamp: new Date(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleQuickQuestion = (question) => {
    sendMessage(question);
  };

  return (
    <>
      {/* Floating Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`ask-ai-button ${isOpen ? 'open' : ''}`}
        title="Ask AI for help"
      >
        {isOpen ? '✕' : '🤖'}
      </button>

      {/* Chat Widget */}
      {isOpen && (
        <div className="ask-ai-widget">
          {/* Header */}
          <div className="widget-header">
            <div className="header-content">
              <div className="avatar">🤖</div>
              <div>
                <h4>AI Help Assistant</h4>
                <p className="status">
                  <span className="status-dot"></span>
                  Online
                </p>
              </div>
            </div>
            <button onClick={() => setIsOpen(false)} className="close-btn">
              ✕
            </button>
          </div>

          {/* Messages */}
          <div className="widget-messages">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`message ${message.role} ${message.isError ? 'error' : ''}`}
              >
                {message.role === 'assistant' && (
                  <div className="message-avatar">🤖</div>
                )}
                <div className="message-bubble">
                  <div className="message-content">
                    {message.content}
                  </div>
                  <span className="message-time">
                    {message.timestamp.toLocaleTimeString([], { 
                      hour: '2-digit', 
                      minute: '2-digit' 
                    })}
                  </span>
                </div>
              </div>
            ))}
            
            {loading && (
              <div className="message assistant">
                <div className="message-avatar">🤖</div>
                <div className="message-bubble typing">
                  <div className="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              </div>
            )}

            {/* Quick Questions */}
            {messages.length === 1 && commonQuestions.length > 0 && (
              <div className="quick-questions">
                <p className="quick-title">💡 Common questions:</p>
                {commonQuestions.slice(0, 3).map((question, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleQuickQuestion(question)}
                    className="quick-question-btn"
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="widget-input">
            <input
              type="text"
              placeholder="Ask anything about the platform..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={loading}
              maxLength={500}
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || loading}
              className="send-btn"
            >
              ➤
            </button>
          </div>
        </div>
      )}

      <style jsx>{`
        .ask-ai-button {
          position: fixed;
          bottom: 24px;
          right: 24px;
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          border: none;
          color: white;
          font-size: 28px;
          cursor: pointer;
          box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
          transition: all 0.3s;
          z-index: 1000;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .ask-ai-button:hover {
          transform: scale(1.1);
          box-shadow: 0 6px 30px rgba(102, 126, 234, 0.6);
        }

        .ask-ai-button.open {
          background: #dc2626;
        }

        .ask-ai-widget {
          position: fixed;
          bottom: 100px;
          right: 24px;
          width: 400px;
          height: 600px;
          background: white;
          border-radius: 16px;
          box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
          display: flex;
          flex-direction: column;
          z-index: 999;
          animation: slideUp 0.3s ease-out;
        }

        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @media (max-width: 480px) {
          .ask-ai-widget {
            width: calc(100vw - 32px);
            height: calc(100vh - 140px);
            right: 16px;
            bottom: 90px;
          }
        }

        .widget-header {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          padding: 16px;
          border-radius: 16px 16px 0 0;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .header-content {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .avatar {
          width: 40px;
          height: 40px;
          background: rgba(255, 255, 255, 0.2);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
        }

        .widget-header h4 {
          margin: 0;
          font-size: 16px;
        }

        .status {
          margin: 4px 0 0 0;
          font-size: 12px;
          opacity: 0.9;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .status-dot {
          width: 6px;
          height: 6px;
          background: #4ade80;
          border-radius: 50%;
          animation: pulse 2s infinite;
        }

        .close-btn {
          background: none;
          border: none;
          color: white;
          font-size: 24px;
          cursor: pointer;
          padding: 4px;
          opacity: 0.8;
          transition: opacity 0.2s;
        }

        .close-btn:hover {
          opacity: 1;
        }

        .widget-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          background: #f9fafb;
        }

        .message {
          margin-bottom: 16px;
          display: flex;
          gap: 8px;
          align-items: flex-start;
          animation: fadeIn 0.3s ease-in;
        }

        .message.user {
          flex-direction: row-reverse;
        }

        .message-avatar {
          width: 28px;
          height: 28px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          flex-shrink: 0;
        }

        .message-bubble {
          max-width: 75%;
          padding: 10px 14px;
          border-radius: 16px;
        }

        .message.assistant .message-bubble {
          background: white;
          border: 1px solid #e5e7eb;
        }

        .message.user .message-bubble {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
        }

        .message.error .message-bubble {
          background: #fee2e2;
          border-color: #fca5a5;
          color: #991b1b;
        }

        .message-content {
          font-size: 14px;
          line-height: 1.5;
          white-space: pre-wrap;
          word-wrap: break-word;
        }

        .message-time {
          font-size: 10px;
          opacity: 0.6;
          margin-top: 4px;
          display: block;
        }

        .typing-indicator {
          display: flex;
          gap: 4px;
          padding: 4px 0;
        }

        .typing-indicator span {
          width: 6px;
          height: 6px;
          background: #9ca3af;
          border-radius: 50%;
          animation: bounce 1.4s infinite ease-in-out both;
        }

        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

        @keyframes bounce {
          0%, 80%, 100% { transform: scale(0); }
          40% { transform: scale(1); }
        }

        .quick-questions {
          margin: 16px 0;
        }

        .quick-title {
          font-size: 12px;
          font-weight: 600;
          color: #6b7280;
          margin: 0 0 8px 0;
        }

        .quick-question-btn {
          display: block;
          width: 100%;
          text-align: left;
          padding: 10px 12px;
          margin-bottom: 6px;
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          font-size: 13px;
          color: #374151;
          cursor: pointer;
          transition: all 0.2s;
        }

        .quick-question-btn:hover {
          background: #f3f4f6;
          border-color: #667eea;
          color: #667eea;
        }

        .widget-input {
          padding: 12px;
          background: white;
          border-top: 1px solid #e5e7eb;
          display: flex;
          gap: 8px;
        }

        .widget-input input {
          flex: 1;
          padding: 10px 12px;
          border: 1px solid #e5e7eb;
          border-radius: 20px;
          font-size: 14px;
          outline: none;
          transition: border-color 0.2s;
        }

        .widget-input input:focus {
          border-color: #667eea;
        }

        .widget-input input:disabled {
          background: #f9fafb;
          cursor: not-allowed;
        }

        .send-btn {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          border: none;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          font-size: 16px;
          cursor: pointer;
          transition: transform 0.2s;
          flex-shrink: 0;
        }

        .send-btn:hover:not(:disabled) {
          transform: scale(1.05);
        }

        .send-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </>
  );
}
