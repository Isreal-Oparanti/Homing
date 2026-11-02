"""Sound from voice notes and videos, for Muse Voice Transcribe (docs/06 · Voice notes).

Meta's endpoint takes WAV only, up to 10 minutes: 16 kHz mono 16-bit. PyAV has its own
decoders, so this works without a system ffmpeg.
"""

import io
import wave

import av

RATE = 16_000
MAX_SECONDS = 600  # the transcription endpoint's limit


class NoSound(ValueError):
    """The file has no sound we can decode. The message is shown to the person."""


def to_wav(data: bytes, max_seconds: int = MAX_SECONDS) -> tuple[bytes, float]:
    """The first `max_seconds` of the file's sound as 16 kHz mono WAV, and the sound's full
    length in seconds."""
    try:
        container = av.open(io.BytesIO(data))
    except av.error.FFmpegError as exc:
        raise NoSound("Couldn't open this file's sound.") from exc
    with container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise NoSound("This file has no sound.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        limit = max_seconds * RATE * 2  # bytes of 16-bit samples
        pcm = bytearray()
        try:
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    pcm += bytes(out.planes[0])[: out.samples * 2]
                if len(pcm) >= limit:
                    break
            for out in resampler.resample(None):
                pcm += bytes(out.planes[0])[: out.samples * 2]
        except av.error.FFmpegError as exc:
            if not pcm:
                raise NoSound("Couldn't decode this file's sound.") from exc
        if stream.duration and stream.time_base:
            seconds = float(stream.duration * stream.time_base)
        elif container.duration:
            seconds = container.duration / 1_000_000
        else:
            seconds = len(pcm) / (RATE * 2)
    if not pcm:
        raise NoSound("This file's sound is empty.")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(pcm[:limit]))
    return buf.getvalue(), seconds
