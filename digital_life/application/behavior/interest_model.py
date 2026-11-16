"""Compatibility import. Experience statistics belong to cognition, not interest."""
from digital_life.application.cognition.cognition_experience import ExperienceProjection

# Historical callers and frozen artifacts keep their import; no separate owner.
InterestModel = ExperienceProjection
