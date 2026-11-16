"""Fresh-request probability prediction port for controlled experience evaluation."""
from typing import Protocol

class PredictionPort(Protocol):
    name:str
    def predict(self,request:dict)->dict:
        """Return probabilities (or null) and actual_tokens; no tools or continuation."""
        ...
