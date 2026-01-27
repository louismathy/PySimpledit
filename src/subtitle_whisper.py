from __future__ import annotations

from typing import List, Optional, Dict


def transcribe_whisper(audio_path: str, model_name: str, language: Optional[str] = None) -> List[Dict[str, float | str]]:
    try:
        import whisper
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "Whisper is not installed. Install it with: pip install openai-whisper"
        ) from exc

    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path, language=language or None, task="transcribe")
    segments = result.get("segments") or []
    out: List[Dict[str, float | str]] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": text,
            }
        )
    return out
