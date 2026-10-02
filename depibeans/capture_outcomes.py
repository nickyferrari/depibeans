"""Outcomes that establish no acquisition trigger was issued."""
class CaptureCancelled(RuntimeError):
    pass
class CaptureSkipped(RuntimeError):
    pass
