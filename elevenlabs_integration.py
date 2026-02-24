import os
import requests
from typing import List, Dict

# ElevenLabs API
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


def get_available_voices() -> Dict:
    """
    Get list of available ElevenLabs voices
    
    Returns:
        {
            "success": bool,
            "voices": [
                {
                    "voice_id": str,
                    "name": str,
                    "description": str,
                    "preview_url": str,
                    "category": str (e.g., "premade", "cloned")
                }
            ],
            "error": str (if failed)
        }
    """
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ElevenLabs API key not configured"}
    
    try:
        response = requests.get(
            f"{ELEVENLABS_API_URL}/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            voices = []
            
            for voice in data.get("voices", []):
                voices.append({
                    "voice_id": voice.get("voice_id"),
                    "name": voice.get("name"),
                    "description": voice.get("description", ""),
                    "preview_url": voice.get("preview_url", ""),
                    "category": voice.get("category", "premade"),
                    "labels": voice.get("labels", {})
                })
            
            return {
                "success": True,
                "voices": voices
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def text_to_speech(text: str, voice_id: str, model_id: str = "eleven_turbo_v2") -> Dict:
    """
    Convert text to speech using ElevenLabs
    
    Args:
        text: Text to convert to speech
        voice_id: ElevenLabs voice ID
        model_id: Model to use (eleven_turbo_v2 is fastest, eleven_multilingual_v2 for more languages)
    
    Returns:
        {
            "success": bool,
            "audio_bytes": bytes (audio data),
            "error": str (if failed)
        }
    """
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ElevenLabs API key not configured"}
    
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
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "audio_bytes": response.content
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_voice_settings(voice_id: str) -> Dict:
    """
    Get current settings for a voice
    
    Args:
        voice_id: ElevenLabs voice ID
    
    Returns:
        Voice settings dict
    """
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ElevenLabs API key not configured"}
    
    try:
        response = requests.get(
            f"{ELEVENLABS_API_URL}/voices/{voice_id}/settings",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "settings": response.json()
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_user_info() -> Dict:
    """
    Get ElevenLabs user subscription info
    
    Returns:
        {
            "success": bool,
            "subscription": {
                "tier": str,
                "character_count": int,
                "character_limit": int,
                "can_use_instant_voice_cloning": bool
            },
            "error": str (if failed)
        }
    """
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ElevenLabs API key not configured"}
    
    try:
        response = requests.get(
            f"{ELEVENLABS_API_URL}/user",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            subscription = data.get("subscription", {})
            
            return {
                "success": True,
                "subscription": {
                    "tier": subscription.get("tier", "free"),
                    "character_count": subscription.get("character_count", 0),
                    "character_limit": subscription.get("character_limit", 0),
                    "can_use_instant_voice_cloning": subscription.get("can_use_instant_voice_cloning", False),
                    "can_use_professional_voice_cloning": subscription.get("can_use_professional_voice_cloning", False)
                }
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}"
            }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


# Popular pre-made voices for quick reference
POPULAR_VOICES = {
    "Rachel": "21m00Tcm4TlvDq8ikWAM",  # American Female - Calm
    "Domi": "AZnzlk1XvdvUeBnXmlld",    # American Female - Strong
    "Bella": "EXAVITQu4vr4xnSDxMaL",   # American Female - Soft
    "Antoni": "ErXwobaYiN019PkySvjV",  # American Male - Well-rounded
    "Elli": "MF3mGyEYCl7XYWbV9V6O",    # American Female - Emotional
    "Josh": "TxGEqnHWrfWFTfGW9XjX",    # American Male - Deep
    "Arnold": "VR6AewLTigWG4xSOukaG",  # American Male - Crisp
    "Adam": "pNInz6obpgDQGcFmaJgB",    # American Male - Deep
    "Sam": "yoZ06aMxZJJ28mfd3POQ"      # American Male - Raspy
}


def get_popular_voices() -> List[Dict]:
    """
    Get list of popular pre-made voices with their IDs
    
    Returns:
        List of popular voice dicts
    """
    return [
        {"name": name, "voice_id": voice_id}
        for name, voice_id in POPULAR_VOICES.items()
    ]
