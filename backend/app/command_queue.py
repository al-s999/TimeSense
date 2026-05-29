"""Command queue for managing door commands"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class Command:
    action: str
    priority: int = 10
    created_at: float = field(default_factory=time.time)
    ttl: int = 300  # 5 minutes
    executed_at: Optional[float] = None
    
    def is_expired(self) -> bool:
        """Check if command has expired"""
        return time.time() - self.created_at > self.ttl
    
    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "priority": self.priority,
            "created_at": self.created_at,
            "ttl": self.ttl,
            "age_seconds": round(time.time() - self.created_at, 2)
        }

class CommandQueue:
    """Manage commands per device"""
    
    def __init__(self):
        self._queues: Dict[str, List[Command]] = {}
        self._lock = threading.Lock()
    
    def enqueue(self, device_id: str, command: Command) -> bool:
        """Add command to queue"""
        with self._lock:
            if device_id not in self._queues:
                self._queues[device_id] = []
            
            # Remove expired commands first
            self._queues[device_id] = [
                c for c in self._queues[device_id]
                if not c.is_expired()
            ]
            
            # Add new command (higher priority first)
            self._queues[device_id].append(command)
            self._queues[device_id].sort(key=lambda c: c.priority, reverse=True)
            
            print(f"[COMMAND] Enqueued {command.action} for {device_id} (priority={command.priority})")
            return True
    
    def dequeue(self, device_id: str) -> Optional[Command]:
        """Get and remove next command"""
        with self._lock:
            if device_id not in self._queues or not self._queues[device_id]:
                return None
            
            # Remove expired commands
            self._queues[device_id] = [
                c for c in self._queues[device_id]
                if not c.is_expired()
            ]
            
            if not self._queues[device_id]:
                return None
            
            command = self._queues[device_id].pop(0)
            command.executed_at = time.time()
            print(f"[COMMAND] Dequeued {command.action} for {device_id}")
            return command
    
    def peek(self, device_id: str) -> Optional[Command]:
        """Look at next command without removing"""
        with self._lock:
            if device_id not in self._queues or not self._queues[device_id]:
                return None
            
            # Remove expired commands first
            self._queues[device_id] = [
                c for c in self._queues[device_id]
                if not c.is_expired()
            ]
            
            if not self._queues[device_id]:
                return None
            
            return self._queues[device_id][0]
    
    def get_queue(self, device_id: str) -> List[Dict]:
        """Get all commands in queue"""
        with self._lock:
            if device_id not in self._queues:
                return []
            return [c.to_dict() for c in self._queues[device_id]]
    
    def clear(self, device_id: str) -> None:
        """Clear all commands for device"""
        with self._lock:
            self._queues[device_id] = []

# Global instance
_command_queue = None

def get_command_queue() -> CommandQueue:
    """Get singleton instance"""
    global _command_queue
    if _command_queue is None:
        _command_queue = CommandQueue()
    return _command_queue
