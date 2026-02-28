import os
import requests
from typing import Dict, List, Optional
import base64

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


def get_available_voices() -> List[Dict]:
    """
    Get list of available ElevenLabs voices
    
    Returns:
        List of voices with id, name, and preview_url
    """
    if not ELEVENLABS_API_KEY:
        return []
    
    try:
        response = requests.get(
            f"{ELEVENLABS_API_URL}/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY}
        )
        
        if response.status_code == 200:
            data = response.json()
            voices = []
            
            for voice in data.get("voices", []):
                voices.append({
                    "voice_id": voice.get("voice_id"),
                    "name": voice.get("name"),
                    "preview_url": voice.get("preview_url"),
                    "category": voice.get("category", "premade"),
                    "labels": voice.get("labels", {}),
                    "description": voice.get("description", "")
                })
            
            return voices
        else:
            print(f"❌ Failed to get ElevenLabs voices: {response.status_code}")
            return []
    
    except Exception as e:
        print(f"❌ Error getting ElevenLabs voices: {e}")
        return []


def text_to_speech(
    text: str,
    voice_id: str,
    model_id: str = "eleven_turbo_v2_5",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True
) -> Optional[bytes]:
    """
    Convert text to speech using ElevenLabs
    
    Args:
        text: Text to convert to speech
        voice_id: ElevenLabs voice ID
        model_id: Model to use (eleven_turbo_v2_5 for low latency)
        stability: Voice stability (0-1)
        similarity_boost: Voice similarity (0-1)
        style: Style exaggeration (0-1)
        use_speaker_boost: Enable speaker boost
    
    Returns:
        Audio bytes or None if failed
    """
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not set")
        return None
    
    try:
        response = requests.post(
            f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": style,
                    "use_speaker_boost": use_speaker_boost
                }
            }
        )
        
        if response.status_code == 200:
            return response.content
        else:
            print(f"❌ ElevenLabs TTS failed: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        print(f"❌ Error calling ElevenLabs TTS: {e}")
        return None


def stream_text_to_speech(
    text: str,
    voice_id: str,
    model_id: str = "eleven_turbo_v2_5",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    output_format: str = "pcm_16000"
):
    """
    Stream text to speech for real-time applications
    
    Args:
        text: Text to convert
        voice_id: ElevenLabs voice ID
        model_id: Model to use (eleven_turbo_v2_5 for low latency)
        stability: Voice stability
        similarity_boost: Voice similarity
        output_format: Audio format
            - pcm_16000: 16kHz PCM (for Twilio, lowest latency)
            - pcm_22050: 22.05kHz PCM
            - pcm_24000: 24kHz PCM  
            - mp3_44100_128: MP3 format
    
    Yields:
        Audio chunks (raw bytes)
    """
    if not ELEVENLABS_API_KEY:
        print("❌ ELEVENLABS_API_KEY not set")
        return
    
    try:
        # Use streaming endpoint for lowest latency
        url = f"{ELEVENLABS_API_URL}/text-to-speech/{voice_id}/stream"
        
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg" if output_format.startswith("mp3") else "audio/raw"
        }
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": 0,
                "use_speaker_boost": True
            }
        }
        
        # Add output format if supported by model
        if model_id == "eleven_turbo_v2_5":
            payload["output_format"] = output_format
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=5  # 5 second timeout for first byte
        )
        
        if response.status_code == 200:
            # Stream audio chunks
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk
        else:
            print(f"❌ ElevenLabs streaming failed: {response.status_code} - {response.text}")
    
    except requests.exceptions.Timeout:
        print(f"⏱️ ElevenLabs request timed out")
    except Exception as e:
        print(f"❌ Error streaming ElevenLabs TTS: {e}")


def get_voice_info(voice_id: str) -> Optional[Dict]:
    """
    Get detailed information about a specific voice
    
    Args:
        voice_id: ElevenLabs voice ID
    
    Returns:
        Voice information or None
    """
    if not ELEVENLABS_API_KEY:
        return None
    
    try:
        response = requests.get(
            f"{ELEVENLABS_API_URL}/voices/{voice_id}",
            headers={"xi-api-key": ELEVENLABS_API_KEY}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    
    except Exception as e:
        print(f"❌ Error getting voice info: {e}")
        return None


def get_user_subscription() -> Optional[Dict]:
    """
    Get ElevenLabs subscription information
    
    Returns:
        Subscription details or None
    """
    if not ELEVENLABS_API_KEY:
        return None
    
    try:
        response = requests.get(
            f"{ELEVENLABS_API_URL}/user/subscription",
            headers={"xi-api-key": ELEVENLABS_API_KEY}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    
    except Exception as e:
        print(f"❌ Error getting subscription: {e}")
        return None


# Popular ElevenLabs voices (as fallback if API is unavailable)
POPULAR_VOICES = [
    {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel",
        "category": "premade",
        "description": "Calm, young, female American voice"
    },
    {
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi",
        "category": "premade",
        "description": "Strong, female American voice"
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella",
        "category": "premade",
        "description": "Soft, young, female American voice"
    },
    {
        "voice_id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni",
        "category": "premade",
        "description": "Well-rounded, young, male American voice"
    },
    {
        "voice_id": "MF3mGyEYCl7XYWbV9V6O",
        "name": "Elli",
        "category": "premade",
        "description": "Emotional, young, female American voice"
    },
    {
        "voice_id": "TxGEqnHWrfWFTfGW9XjX",
        "name": "Josh",
        "category": "premade",
        "description": "Deep, young, male American voice"
    },
    {
        "voice_id": "VR6AewLTigWG4xSOukaG",
        "name": "Arnold",
        "category": "premade",
        "description": "Crisp, middle-aged, male American voice"
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam",
        "category": "premade",
        "description": "Deep, middle-aged, male American voice"
    },
    {
        "voice_id": "yoZ06aMxZJJ28mfd3POQ",
        "name": "Sam",
        "category": "premade",
        "description": "Raspy, young, male American voice"
    }
]


def get_all_voice_options() -> Dict:
    """
    Get all available voice options from both OpenAI and ElevenLabs
    
    Returns:
        {
            "openai": [...],
            "elevenlabs": [...]
        }
    """
    # OpenAI voices
    openai_voices = [
        {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced voice"},
        {"id": "echo", "name": "Echo", "description": "Warm, friendly voice"},
        {"id": "fable", "name": "Fable", "description": "Expressive, storytelling voice"},
        {"id": "onyx", "name": "Onyx", "description": "Deep, authoritative voice"},
        {"id": "nova", "name": "Nova", "description": "Energetic, bright voice"},
        {"id": "shimmer", "name": "Shimmer", "description": "Soft, gentle voice"},
        {"id": "ash", "name": "Ash", "description": "Clear, professional voice"},
        {"id": "ballad", "name": "Ballad", "description": "Smooth, calm voice"},
        {"id": "coral", "name": "Coral", "description": "Warm, engaging voice"},
        {"id": "sage", "name": "Sage", "description": "Wise, thoughtful voice"},
        {"id": "verse", "name": "Verse", "description": "Dynamic, expressive voice"}
    ]
    
    # Get ElevenLabs voices
    elevenlabs_voices = get_available_voices()
    
    # If API call failed, use popular voices as fallback
    if not elevenlabs_voices:
        elevenlabs_voices = POPULAR_VOICES
    
    return {
        "openai": openai_voices,
        "elevenlabs": elevenlabs_voices
    }
