"""Minimal pydantic models for FHIR R4 resources consumed by Vigil.

Only fields we actually read are modelled. Everything else is ignored via
model_config extra="ignore".

References:
- HL7 FHIR R4: https://hl7.org/fhir/R4/
- Observation vital-signs profile: https://hl7.org/fhir/R4/observation-vitalsigns.html
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Coding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Reference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reference: str | None = None
    display: str | None = None


class Quantity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: float | None = None
    unit: str | None = None
    system: str | None = None
    code: str | None = None


class Period(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: datetime | None = None
    end: datetime | None = None


class Identifier(BaseModel):
    model_config = ConfigDict(extra="ignore")

    system: str | None = None
    value: str | None = None


class HumanName(BaseModel):
    model_config = ConfigDict(extra="ignore")

    family: str | None = None
    given: list[str] = Field(default_factory=list)


class CategoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    coding: list[Coding] = Field(default_factory=list)


class Dosage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dose: Quantity | None = None
    route: CodeableConcept | None = None


class NoteItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str | None = None


# ---------------------------------------------------------------------------
# FHIR R4 resources
# ---------------------------------------------------------------------------


class Patient(BaseModel):
    """FHIR R4 Patient resource (minimal)."""

    model_config = ConfigDict(extra="ignore")

    resourceType: str = "Patient"
    id: str | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    name: list[HumanName] = Field(default_factory=list)
    gender: str | None = None
    birthDate: str | None = None


class Observation(BaseModel):
    """FHIR R4 Observation resource (vital-signs and laboratory)."""

    model_config = ConfigDict(extra="ignore")

    resourceType: str = "Observation"
    id: str | None = None
    status: str | None = None
    category: list[CategoryItem] = Field(default_factory=list)
    code: CodeableConcept | None = None
    subject: Reference | None = None
    encounter: Reference | None = None
    effectiveDateTime: datetime | None = None
    valueQuantity: Quantity | None = None
    note: list[NoteItem] = Field(default_factory=list)

    @property
    def loinc_code(self) -> str | None:
        """Extract the first LOINC code from code.coding."""
        if self.code:
            for c in self.code.coding:
                if c.system == "http://loinc.org" and c.code:
                    return c.code
        return None

    @property
    def category_code(self) -> str | None:
        """Extract first category code (e.g. 'vital-signs' or 'laboratory')."""
        for cat in self.category:
            for c in cat.coding:
                if c.code:
                    return c.code
        return None


class Condition(BaseModel):
    """FHIR R4 Condition resource."""

    model_config = ConfigDict(extra="ignore")

    resourceType: str = "Condition"
    id: str | None = None
    clinicalStatus: CodeableConcept | None = None
    verificationStatus: CodeableConcept | None = None
    code: CodeableConcept | None = None
    subject: Reference | None = None
    recordedDate: str | None = None


class Encounter(BaseModel):
    """FHIR R4 Encounter resource."""

    model_config = ConfigDict(extra="ignore")

    resourceType: str = "Encounter"
    id: str | None = None
    status: str | None = None
    subject: Reference | None = None
    period: Period | None = None


class MedicationAdministration(BaseModel):
    """FHIR R4 MedicationAdministration resource."""

    model_config = ConfigDict(extra="ignore")

    resourceType: str = "MedicationAdministration"
    id: str | None = None
    status: str | None = None
    medicationCodeableConcept: CodeableConcept | None = None
    subject: Reference | None = None
    effectiveDateTime: datetime | None = None
    dosage: Dosage | None = None


class DosageInstruction(BaseModel):
    """FHIR R4 Dosage backbone — used by MedicationRequest.dosageInstruction."""

    model_config = ConfigDict(extra="ignore")

    text: str | None = None
    route: CodeableConcept | None = None


class MedicationRequest(BaseModel):
    """FHIR R4 MedicationRequest resource (active orders).

    Used by ``flag_treatment_conflicts`` to detect drugs that have been
    *ordered* but not necessarily administered yet — pre-emptive safety
    check before the next dose lands. Mirrors the minimal-fields shape
    of :class:`MedicationAdministration`.
    """

    model_config = ConfigDict(extra="ignore")

    resourceType: str = "MedicationRequest"
    id: str | None = None
    status: str | None = None
    intent: str | None = None
    medicationCodeableConcept: CodeableConcept | None = None
    medicationReference: Reference | None = None
    subject: Reference | None = None
    authoredOn: datetime | None = None
    dosageInstruction: list[DosageInstruction] = Field(default_factory=list)
