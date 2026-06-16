from pydantic import BaseModel

VALID_CATEGORIES = {
    "compatibility",
    "incompatibility",
    "substitution",
    "specification",
    "sizing_rule",
    "installation_procedure",
    "installation_requirement",
    "maintenance_procedure",
    "maintenance_interval",
    "diagnostic_sign",
    "diagnostic_procedure",
    "failure_mode",
    "safety_warning",
    "regulatory_requirement",
    "ordering_pattern",
    "application_condition",
}


class ExtractedFact(BaseModel):
    fact: str
    category: str
    entities: list[str]
    source_quote: str
    interpretation_confidence: float
