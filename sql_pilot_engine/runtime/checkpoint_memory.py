from langgraph.checkpoint.memory import InMemorySaver

from sql_pilot_engine.runtime.checkpoint import (
    CheckpointStore,
)

class MemoryCheckpointStore:
    
    def __init__(self) -> None:
        self._bankend = InMemorySaver()
        
    def get_backend(self):
        return self._bankend