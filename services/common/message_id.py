"""Message ID generation for correlation tracking."""

import uuid
from typing import Optional


def generate_message_id(prefix: Optional[str] = None) -> str:
    """Generate a unique message correlation ID.
    
    Args:
        prefix: Optional prefix for the ID (e.g., 'msg', 'evt')
        
    Returns:
        Unique identifier string
    """
    uid = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{uid}"
    return uid


def generate_conversation_id() -> str:
    """Generate a conversation/thread ID.
    
    Returns:
        Unique conversation identifier
    """
    return f"conv_{uuid.uuid4().hex[:16]}"
