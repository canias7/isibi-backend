import React, { useState, useRef, useEffect } from 'react';

/**
 * Test Agent Voice Interface
 * 
 * Allows users to test their AI agent with voice before deploying
 * Shows live transcript of the conversation
 */

export default function TestAgentModal({ agent, token, onClose }) {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcript, setTranscript] = useState([]);
  const [error, setError] = useState(null);
  const [duration, setDuration] = useState(0);
  
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const durationIntervalRef = useRef(null);

  // Start test call
  const startTest = async () => {
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
      
      // Connect to test agent WebSocket
      const wsUrl = `wss://your-backend.onrender.com/test-agent/${agent.id}?token=${token}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('✅ Connected to test agent');
        setIsConnected(true);
        setIsRecording(true);
        startMicrophoneStreaming(stream);
        
        // Start duration timer
        durationIntervalRef.current = setInterval(() => {
          setDuration(d => d + 1);
        }, 1000);
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
        console.log('❌ Disconnected from test agent');
        setIsConnected(false);
        setIsRecording(false);
        stopMicrophoneStreaming();
        
        if (durationIntervalRef.current) {
          clearInterval(durationIntervalRef.current);
        }
      };
      
    } catch (err) {
      console.error('Failed to start test:', err);
      setError('Microphone access denied. Please allow microphone to test your agent.');
    }
  };

  // Stop test call
  const stopTest = () => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: 'end' }));
      wsRef.current.close();
    }
    
    stopMicrophoneStreaming();
    setIsConnected(false);
    setIsRecording(false);
    
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current);
    }
  };

  // Start streaming microphone audio
  const startMicrophoneStreaming = (stream) => {
    const audioContext = audioContextRef.current;
    const source = audioContext.createMediaStreamSource(stream);
    
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
    
    if (type === 'conversation.item.input_audio_transcription.completed') {
      // User's speech transcribed
      setTranscript(prev => [...prev, {
        role: 'user',
        content: data.transcript,
        timestamp: new Date()
      }]);
    } else if (type === 'response.audio_transcript.delta') {
      // AI's response transcript
      setTranscript(prev => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && !last.complete) {
          return [
            ...prev.slice(0, -1),
            { ...last, content: last.content + data.delta }
          ];
        } else {
          return [...prev, {
            role: 'assistant',
            content: data.delta,
            timestamp: new Date(),
            complete: false
          }];
        }
      });
    } else if (type === 'response.audio_transcript.done') {
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
      setError(data.error);
      stopTest();
    }
  };

  // Format duration
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopTest();
    };
  }, []);

  return (
    <div className="test-agent-modal-overlay" onClick={onClose}>
      <div className="test-agent-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <h2>🎤 Test Agent: {agent.name}</h2>
            <p className="subtitle">Have a voice conversation to test your agent</p>
          </div>
          <button onClick={onClose} className="close-btn">✕</button>
        </div>

        {/* Content */}
        <div className="modal-content">
          {!isConnected ? (
            /* Start Screen */
            <div className="start-screen">
              <div className="agent-info">
                <div className="info-row">
                  <span className="label">Voice:</span>
                  <span className="value">{agent.voice || 'alloy'}</span>
                </div>
                <div className="info-row">
                  <span className="label">Prompt:</span>
                  <span className="value">{agent.system_prompt?.substring(0, 100)}...</span>
                </div>
              </div>

              {error && (
                <div className="error-message">
                  ⚠️ {error}
                </div>
              )}

              <button onClick={startTest} className="start-test-btn">
                🎙️ Start Test Call
              </button>

              <div className="info-box">
                <p><strong>💡 How it works:</strong></p>
                <p>Click the button above to start a voice call with your agent. You'll be able to speak naturally and hear how your agent responds.</p>
              </div>
            </div>
          ) : (
            /* Active Call Screen */
            <div className="active-call">
              {/* Status */}
              <div className="call-status">
                <div className="status-indicator">
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
                </div>
                
                <p className="status-text">
                  {isSpeaking ? `${agent.name} is speaking...` : "Listening... speak now"}
                </p>
                
                <p className="duration">⏱️ {formatDuration(duration)}</p>
              </div>

              {/* Transcript */}
              <div className="test-transcript">
                <h4>Conversation Transcript</h4>
                <div className="transcript-messages">
                  {transcript.length === 0 ? (
                    <p className="empty-state">Start speaking to test your agent</p>
                  ) : (
                    transcript.map((msg, idx) => (
                      <div key={idx} className={`transcript-msg ${msg.role}`}>
                        <div className="msg-role">
                          {msg.role === 'user' ? '👤 You' : `🤖 ${agent.name}`}
                        </div>
                        <div className="msg-content">{msg.content}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* End Button */}
              <button onClick={stopTest} className="end-test-btn">
                ❌ End Test Call
              </button>
            </div>
          )}
        </div>
      </div>

      <style jsx>{`
        .test-agent-modal-overlay {
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

        .test-agent-modal {
          background: white;
          border-radius: 16px;
          max-width: 700px;
          width: 100%;
          max-height: 90vh;
          display: flex;
          flex-direction: column;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
          animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
          from {
            opacity: 0;
            transform: scale(0.95);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }

        .modal-header {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          padding: 24px;
          border-radius: 16px 16px 0 0;
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
        }

        .modal-header h2 {
          margin: 0;
          font-size: 22px;
        }

        .subtitle {
          margin: 6px 0 0 0;
          font-size: 14px;
          opacity: 0.9;
        }

        .close-btn {
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: white;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          font-size: 20px;
          cursor: pointer;
          transition: background 0.2s;
        }

        .close-btn:hover {
          background: rgba(255, 255, 255, 0.3);
        }

        .modal-content {
          padding: 32px;
          overflow-y: auto;
        }

        .start-screen {
          text-align: center;
        }

        .agent-info {
          background: #f9fafb;
          border-radius: 12px;
          padding: 20px;
          margin-bottom: 24px;
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          padding: 12px 0;
          border-bottom: 1px solid #e5e7eb;
        }

        .info-row:last-child {
          border-bottom: none;
        }

        .label {
          font-weight: 600;
          color: #6b7280;
        }

        .value {
          color: #1f2937;
          text-align: right;
          max-width: 60%;
        }

        .start-test-btn {
          padding: 16px 48px;
          font-size: 18px;
          font-weight: 600;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 50px;
          cursor: pointer;
          transition: all 0.3s;
          margin: 24px 0;
        }

        .start-test-btn:hover {
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
          text-align: left;
          color: #0369a1;
        }

        .info-box p {
          margin: 0 0 8px 0;
        }

        .info-box p:last-child {
          margin: 0;
        }

        .call-status {
          text-align: center;
          padding: 32px 0;
          border-bottom: 1px solid #e5e7eb;
          margin-bottom: 24px;
        }

        .status-indicator {
          height: 100px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .speaking-animation {
          display: flex;
          justify-content: center;
          align-items: center;
          gap: 6px;
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
          margin: 16px 0 8px 0;
          font-size: 18px;
          font-weight: 600;
          color: #667eea;
        }

        .duration {
          font-size: 14px;
          color: #6b7280;
        }

        .test-transcript {
          margin-bottom: 24px;
        }

        .test-transcript h4 {
          margin: 0 0 16px 0;
          font-size: 16px;
        }

        .transcript-messages {
          background: #f9fafb;
          border-radius: 12px;
          padding: 16px;
          max-height: 300px;
          overflow-y: auto;
        }

        .empty-state {
          text-align: center;
          color: #9ca3af;
          padding: 32px 16px;
        }

        .transcript-msg {
          margin-bottom: 12px;
          padding: 10px;
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
          font-size: 13px;
          margin-bottom: 6px;
        }

        .msg-content {
          font-size: 14px;
          line-height: 1.5;
        }

        .end-test-btn {
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

        .end-test-btn:hover {
          background: #b91c1c;
        }
      `}</style>
    </div>
  );
}
