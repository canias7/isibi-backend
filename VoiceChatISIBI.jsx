import React, { useState, useRef, useEffect } from 'react';

/**
 * Voice Chat with ISIBI
 * 
 * Features:
 * - Real-time voice conversation with AI
 * - Microphone recording
 * - Speech-to-speech interaction
 * - Visual feedback (waveform, speaking indicators)
 * - Conversation transcript
 */

export default function VoiceChatISIBI() {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [error, setError] = useState(null);
  
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  // Start voice chat
  const startChat = async () => {
    try {
      setError(null);
      
      // Request microphone permission
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 24000
        } 
      });
      
      mediaStreamRef.current = stream;
      
      // Create audio context
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 24000
      });
      
      // Connect to voice chat WebSocket
      const ws = new WebSocket('wss://your-backend.onrender.com/voice-chat');
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('✅ Connected to voice chat');
        setIsConnected(true);
        setIsRecording(true);
        startMicrophoneStreaming(stream);
      };
      
      ws.onmessage = async (event) => {
        if (event.data instanceof Blob) {
          // Audio chunk from AI
          const audioData = await event.data.arrayBuffer();
          playAudioChunk(audioData);
        } else {
          // JSON event
          const data = JSON.parse(event.data);
          handleServerEvent(data);
        }
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setError('Connection error. Please try again.');
      };
      
      ws.onclose = () => {
        console.log('❌ Disconnected from voice chat');
        setIsConnected(false);
        setIsRecording(false);
        stopMicrophoneStreaming();
      };
      
    } catch (err) {
      console.error('Failed to start chat:', err);
      setError('Microphone access denied. Please allow microphone to use voice chat.');
    }
  };

  // Stop voice chat
  const stopChat = () => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: 'end' }));
      wsRef.current.close();
    }
    
    stopMicrophoneStreaming();
    setIsConnected(false);
    setIsRecording(false);
  };

  // Start streaming microphone audio
  const startMicrophoneStreaming = (stream) => {
    const audioContext = audioContextRef.current;
    const source = audioContext.createMediaStreamSource(stream);
    
    // Create script processor for audio chunks
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;
    
    processor.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      
      const inputData = e.inputBuffer.getChannelData(0);
      
      // Convert Float32Array to Int16Array (PCM16)
      const pcm16 = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      
      // Send to server
      wsRef.current.send(pcm16.buffer);
    };
    
    source.connect(processor);
    processor.connect(audioContext.destination);
  };

  // Stop microphone streaming
  const stopMicrophoneStreaming = () => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
    
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  };

  // Play audio chunk from AI
  const playAudioChunk = async (audioData) => {
    audioQueueRef.current.push(audioData);
    
    if (!isPlayingRef.current) {
      playNextChunk();
    }
  };

  // Play next audio chunk in queue
  const playNextChunk = async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsSpeaking(false);
      return;
    }
    
    isPlayingRef.current = true;
    setIsSpeaking(true);
    
    const audioData = audioQueueRef.current.shift();
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    
    try {
      const audioBuffer = await audioContext.decodeAudioData(audioData);
      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);
      
      source.onended = () => {
        playNextChunk();
      };
      
      source.start();
    } catch (err) {
      console.error('Error playing audio:', err);
      playNextChunk();
    }
  };

  // Handle server events
  const handleServerEvent = (data) => {
    const { type } = data;
    
    if (type === 'session.ready') {
      // Connection ready
      console.log('✅ Session ready');
    } else if (type === 'transcript.user.complete') {
      // User's speech transcribed - add complete message
      setTranscript(prev => [...prev, {
        role: 'user',
        content: data.content,
        timestamp: new Date()
      }]);
    } else if (type === 'transcript.assistant.delta') {
      // AI's response transcript (live streaming)
      setTranscript(prev => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && !last.complete) {
          // Update existing message
          return [
            ...prev.slice(0, -1),
            { ...last, content: last.content + data.content }
          ];
        } else {
          // Start new message
          return [...prev, {
            role: 'assistant',
            content: data.content,
            timestamp: new Date(),
            complete: false
          }];
        }
      });
    } else if (type === 'transcript.assistant.complete') {
      // AI finished speaking - mark as complete
      setTranscript(prev => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant') {
          return [
            ...prev.slice(0, -1),
            { ...last, complete: true }
          ];
        }
        return prev;
      });
    } else if (type === 'error') {
      setError(data.error || 'An error occurred');
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopChat();
    };
  }, []);

  return (
    <div className="voice-chat-container">
      <div className="voice-chat-card">
        {/* Header */}
        <div className="chat-header">
          <div className="header-content">
            <div className="avatar">🎤</div>
            <div>
              <h2>Talk to ISIBI</h2>
              <p className="subtitle">Have a voice conversation with our AI</p>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="chat-content">
          {!isConnected ? (
            /* Start Screen */
            <div className="start-screen">
              <div className="microphone-icon">
                🎙️
              </div>
              <h3>Ready to chat?</h3>
              <p>Click the button below to start a voice conversation with ISIBI</p>
              
              {error && (
                <div className="error-message">
                  ⚠️ {error}
                </div>
              )}
              
              <button onClick={startChat} className="start-button">
                🎤 Start Voice Chat
              </button>
              
              <div className="info-box">
                <p><strong>💡 Tip:</strong> Make sure your microphone is enabled</p>
              </div>
            </div>
          ) : (
            /* Active Chat Screen */
            <div className="active-chat">
              {/* Visual Indicator */}
              <div className="voice-indicator">
                {isSpeaking ? (
                  <div className="speaking-animation">
                    <div className="wave"></div>
                    <div className="wave"></div>
                    <div className="wave"></div>
                    <div className="wave"></div>
                    <div className="wave"></div>
                  </div>
                ) : (
                  <div className="listening-animation">
                    <div className="pulse"></div>
                    <div className="microphone">🎙️</div>
                  </div>
                )}
                
                <p className="status-text">
                  {isSpeaking ? "ISIBI is speaking..." : "Listening... speak now"}
                </p>
              </div>

              {/* Transcript */}
              <div className="transcript">
                <h4>📝 Live Conversation</h4>
                <div className="transcript-messages">
                  {transcript.length === 0 ? (
                    <p className="empty-state">Conversation will appear here as you speak...</p>
                  ) : (
                    transcript.map((msg, idx) => (
                      <div key={idx} className={`transcript-msg ${msg.role}`}>
                        <div className="msg-header">
                          <span className="msg-role">
                            {msg.role === 'user' ? '👤 You' : '🤖 ISIBI'}
                          </span>
                          <span className="msg-time">
                            {msg.timestamp.toLocaleTimeString([], { 
                              hour: '2-digit', 
                              minute: '2-digit',
                              second: '2-digit'
                            })}
                          </span>
                        </div>
                        <div className="msg-content">{msg.content}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* End Button */}
              <button onClick={stopChat} className="end-button">
                ❌ End Conversation
              </button>
            </div>
          )}
        </div>
      </div>

      <style jsx>{`
        .voice-chat-container {
          max-width: 800px;
          margin: 0 auto;
          padding: 20px;
        }

        .voice-chat-card {
          background: white;
          border-radius: 16px;
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
          overflow: hidden;
        }

        .chat-header {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          padding: 30px;
        }

        .header-content {
          display: flex;
          align-items: center;
          gap: 20px;
        }

        .avatar {
          width: 60px;
          height: 60px;
          background: rgba(255, 255, 255, 0.2);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 30px;
        }

        .chat-header h2 {
          margin: 0;
          font-size: 28px;
        }

        .subtitle {
          margin: 8px 0 0 0;
          opacity: 0.9;
          font-size: 16px;
        }

        .chat-content {
          padding: 40px;
        }

        .start-screen {
          text-align: center;
        }

        .microphone-icon {
          font-size: 80px;
          margin-bottom: 20px;
          animation: float 3s ease-in-out infinite;
        }

        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-20px); }
        }

        .start-screen h3 {
          font-size: 24px;
          margin: 0 0 10px 0;
        }

        .start-screen p {
          color: #666;
          margin-bottom: 30px;
        }

        .start-button {
          padding: 16px 40px;
          font-size: 18px;
          font-weight: 600;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 50px;
          cursor: pointer;
          transition: all 0.3s;
        }

        .start-button:hover {
          transform: translateY(-2px);
          box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }

        .error-message {
          background: #fee2e2;
          color: #dc2626;
          padding: 12px 20px;
          border-radius: 8px;
          margin: 20px 0;
        }

        .info-box {
          background: #f0f9ff;
          border: 1px solid #bae6fd;
          border-radius: 8px;
          padding: 16px;
          margin-top: 30px;
          color: #0369a1;
        }

        .info-box p {
          margin: 0;
        }

        .voice-indicator {
          text-align: center;
          padding: 40px 0;
        }

        .speaking-animation {
          display: flex;
          justify-content: center;
          align-items: center;
          gap: 6px;
          height: 100px;
        }

        .wave {
          width: 6px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          border-radius: 3px;
          animation: wave 1.2s ease-in-out infinite;
        }

        .wave:nth-child(1) { animation-delay: 0s; }
        .wave:nth-child(2) { animation-delay: 0.1s; }
        .wave:nth-child(3) { animation-delay: 0.2s; }
        .wave:nth-child(4) { animation-delay: 0.3s; }
        .wave:nth-child(5) { animation-delay: 0.4s; }

        @keyframes wave {
          0%, 100% { height: 20px; }
          50% { height: 80px; }
        }

        .listening-animation {
          position: relative;
          height: 100px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .pulse {
          position: absolute;
          width: 100px;
          height: 100px;
          border: 3px solid #667eea;
          border-radius: 50%;
          animation: pulse 2s ease-out infinite;
        }

        @keyframes pulse {
          0% {
            transform: scale(0.8);
            opacity: 1;
          }
          100% {
            transform: scale(1.5);
            opacity: 0;
          }
        }

        .microphone {
          font-size: 50px;
          position: relative;
          z-index: 1;
        }

        .status-text {
          margin-top: 20px;
          font-size: 18px;
          font-weight: 600;
          color: #667eea;
        }

        .transcript {
          margin: 40px 0;
        }

        .transcript h4 {
          margin: 0 0 20px 0;
          font-size: 18px;
          color: #333;
        }

        .transcript-messages {
          background: #f9fafb;
          border-radius: 12px;
          padding: 20px;
          max-height: 300px;
          overflow-y: auto;
        }

        .empty-state {
          text-align: center;
          color: #9ca3af;
          padding: 40px 20px;
        }

        .transcript-msg {
          margin-bottom: 16px;
          padding: 12px;
          border-radius: 8px;
        }

        .transcript-msg.user {
          background: #ede9fe;
          border-left: 4px solid #7c3aed;
        }

        .transcript-msg.assistant {
          background: #dbeafe;
          border-left: 4px solid #3b82f6;
        }

        .msg-role {
          font-weight: 600;
          font-size: 14px;
          margin-bottom: 6px;
        }

        .msg-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }

        .msg-time {
          font-size: 11px;
          color: #6b7280;
          font-weight: 500;
        }

        .msg-content {
          line-height: 1.5;
          font-size: 15px;
          color: #1f2937;
        }

        .end-button {
          width: 100%;
          padding: 14px;
          font-size: 16px;
          font-weight: 600;
          background: #dc2626;
          color: white;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: background 0.3s;
        }

        .end-button:hover {
          background: #b91c1c;
        }
      `}</style>
    </div>
  );
}
