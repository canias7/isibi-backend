import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from db import create_tenant_if_missing, set_agent_prompt, get_agent_prompt

load_dotenv()

router = APIRouter(prefix="/api/prompt", tags=["Prompt Builder"])

# OpenAI client
from openai import OpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

MODEL = os.getenv("PROMPT_MODEL", "gpt-4o-mini")


class PromptGenerateRequest(BaseModel):
    phone_number: str = Field(..., example="+17042017393")
    business_name: str
    business_type: str
    location: str | None = None
    services: list[str] = []
    hours: str | None = None
    tone: str = "professional, friendly"
    languages: list[str] = ["English"]
    booking_instructions: str | None = None


class PromptSaveRequest(BaseModel):
    phone_number: str
    prompt: str


@router.post("/generate")
def generate_prompt(payload: PromptGenerateRequest):
    create_tenant_if_missing(payload.phone_number)

    services_text = "\n".join([f"- {s}" for s in payload.services]) if payload.services else "- (not provided)"
    languages_text = ", ".join(payload.languages) if payload.languages else "English"

    prompt = f"""
Write a SYSTEM PROMPT for an AI receptionist / appointment setter.

Must:
- be clear and structured with sections + bullet points
- ask clarifying questions before booking
- collect: caller name, callback number, reason for call, preferred date/time
- handle English/Spanish if requested
- never invent prices/policies; if unknown, say you’ll confirm or connect them
- be friendly but business-professional

Business:
- Name: {payload.business_name}
- Type: {payload.business_type}
- Location: {payload.location or "Not provided"}
- Hours: {payload.hours or "Not provided"}
- Services:
{services_text}
- Tone: {payload.tone}
- Languages: {languages_text}
- Booking instructions: {payload.booking_instructions or "Not provided"}

Return ONLY the final system prompt text.
""".strip()

    try:
        resp = client.responses.create(
            model=MODEL,
            input=prompt,
        )
        system_prompt = resp.output_text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")

    return {"phone_number": payload.phone_number, "prompt": system_prompt}


@router.post("/save")
def save_prompt(payload: PromptSaveRequest):
    create_tenant_if_missing(payload.phone_number)
    set_agent_prompt(payload.phone_number, payload.prompt)
    return {"ok": True}


@router.get("/get")
def get_prompt(phone_number: str):
    prompt = get_agent_prompt(phone_number)
    if not prompt:
        raise HTTPException(status_code=404, detail="No prompt found for that phone_number")
    return {"phone_number": phone_number, "prompt": prompt}

