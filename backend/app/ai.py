"""Evidence assessment: deterministic image checks + a pluggable multimodal AI provider.

The AI supports the inspector; it does not decide. Its output is validated against a
schema and stored as advisory data. Workflow consequences live in workflow.py.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from PIL import Image, ImageFilter, ImageOps, ImageStat
from pydantic import BaseModel, Field, ValidationError

from .config import settings

MAX_EDGE = 1568


# ----------------------------------------------------------- image intake --

def normalize_image(raw: bytes) -> tuple[bytes, Image.Image]:
    """Decode, apply EXIF orientation, strip metadata (incl. GPS), downscale, re-encode as JPEG."""
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), img


def image_checks(img: Image.Image) -> dict[str, Any]:
    """Cheap, deterministic, non-AI quality heuristics. Thresholds are rough and documented as such."""
    gray = img.convert("L")
    small = gray.copy()
    small.thumbnail((512, 512))
    brightness = ImageStat.Stat(small).mean[0]
    lap = small.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128))
    sharpness = ImageStat.Stat(lap).var[0]
    issues = []
    if min(img.size) < 480:
        issues.append("Low resolution")
    if brightness < 45:
        issues.append("Image appears too dark")
    elif brightness > 225:
        issues.append("Image appears overexposed")
    if sharpness < 30:
        issues.append("Image may be blurred")
    return {
        "method": "deterministic heuristics (not AI)",
        "width": img.size[0], "height": img.size[1],
        "brightness": round(brightness, 1), "sharpness": round(sharpness, 1),
        "issues": issues, "passed": not issues,
    }


# ------------------------------------------------------------ AI contract --

class AssessmentResult(BaseModel):
    summary: str = Field(description="One or two sentences for the inspector.")
    correct_area_visible: Literal["yes", "no", "uncertain"]
    image_quality: Literal["good", "acceptable", "poor"]
    evidence_sufficient: bool
    observations: list[str]
    conditions_for_human_review: list[str]
    missing_information: list[str]
    recommended_action: Literal["accept_for_human_review", "retake_photo", "flag_for_human_review"]
    retake_guidance: str
    uncertainty: Literal["low", "medium", "high"]
    limitations: list[str]


ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "correct_area_visible": {"type": "string", "enum": ["yes", "no", "uncertain"]},
        "image_quality": {"type": "string", "enum": ["good", "acceptable", "poor"]},
        "evidence_sufficient": {"type": "boolean"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "conditions_for_human_review": {"type": "array", "items": {"type": "string"}},
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "recommended_action": {"type": "string",
                               "enum": ["accept_for_human_review", "retake_photo", "flag_for_human_review"]},
        "retake_guidance": {"type": "string"},
        "uncertainty": {"type": "string", "enum": ["low", "medium", "high"]},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "correct_area_visible", "image_quality", "evidence_sufficient", "observations",
                 "conditions_for_human_review", "missing_information", "recommended_action", "retake_guidance",
                 "uncertainty", "limitations"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You assist a human field inspector by reviewing one photograph submitted as evidence for one \
manufacturer-defined inspection requirement on a physical product.

Your job is to judge the photograph as evidence, not to certify the product:
- Decide whether the component and area named in the requirement are actually visible, and whether the image is \
clear enough for a person to judge the acceptance criteria.
- Describe only conditions you can see. Never invent components, defects, measurements, materials or specifications.
- Do not claim that torque, tightness, load capacity, dimensions, tolerances or internal condition are acceptable; \
these cannot be established from a photograph. Say so in limitations when relevant.
- Never state that the product is safe, compliant, approved or released. The inspector and supervisor decide.
- For electrical equipment: never state that an installation is electrically safe, de-energized, correctly wired \
or compliant with any standard, and never infer voltage, continuity, insulation resistance, terminal torque or \
internal operation from a photograph. You may describe visible signs (discoloration, melting, missing labels, \
exposed conductors, loose-looking or disconnected wires, missing covers) as conditions for human review.
- Do not identify brands, part numbers or certifications that are not legible in the image.
- If the photo shows a different object, the wrong part, or is too dark, blurred, distant or obstructed to judge the \
requirement, set evidence_sufficient to false, recommended_action to "retake_photo", and give specific retake_guidance.
- If the required area is visible and something might be a defect (crack, deformation, missing part, damage, \
corrosion), list it under conditions_for_human_review and use "flag_for_human_review".
- Otherwise use "accept_for_human_review". This means "usable evidence", not "requirement passed".
- The asset may be anything from furniture to an industrial control panel; assess what is in the photo against \
the requirement text and asset context as written. Technical values marked as demonstration data are not verified.
Keep every string short and concrete. Write retake_guidance as an empty string when no retake is needed."""


@dataclass
class AssessmentOutcome:
    provider: str
    model: str | None
    status: Literal["completed", "unavailable", "failed", "refused"]
    result: dict[str, Any] | None
    error: str | None
    latency_ms: int


class AssessmentProvider(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...

    def assess(self, image_jpeg: bytes, context: dict[str, Any]) -> AssessmentOutcome: ...


def build_context(*, manifest: dict[str, Any], procedure: dict[str, Any], component: dict[str, Any],
                  requirement: dict[str, Any], serial_number: str, worker_note: str | None,
                  image_checks: dict[str, Any] | None, inspection_id: str | None = None) -> dict[str, Any]:
    """Asset-agnostic assessment context, built the same way for live calls and precomputed demo results."""
    return {
        "industry": manifest.get("industry") or "General",
        "asset_category": manifest.get("asset_category") or "",
        "product_id": manifest["product_id"], "product_name": manifest["product_name"],
        "revision": manifest["engineering_revision"], "serial_number": serial_number,
        "profile_guidance": procedure.get("ai_guidance") or "",
        "component_id": component["component_id"], "component_name": component["name"],
        "component_category": component.get("category") or "", "part_number": component["part_number"],
        "quantity": component["quantity"], "component_description": component.get("description"),
        "specs": component.get("specs", []),
        "requirement": requirement, "worker_note": worker_note, "image_checks": image_checks or {},
        "inspection_id": inspection_id,
    }


def build_prompt(ctx: dict[str, Any]) -> str:
    req = ctx["requirement"]
    specs = "; ".join(f"{s['label']}: {s['value']}{' (demonstration value, unverified)' if s.get('demo_value') else ''}"
                      for s in ctx.get("specs") or []) or "(none)"
    lines = [
        f"Industry: {ctx.get('industry')}. Asset category: {ctx.get('asset_category') or 'n/a'}",
        f"Asset: {ctx['product_name']} ({ctx['product_id']}), engineering revision {ctx['revision']}",
        f"Asset instance: {ctx['serial_number']}",
        f"Inspection profile guidance: {ctx.get('profile_guidance') or '(none)'}",
        f"Component: {ctx['component_name']} ({ctx['component_id']}), category {ctx.get('component_category') or 'n/a'}, "
        f"part number {ctx['part_number']}, quantity {ctx['quantity']}",
        f"Component description: {ctx.get('component_description') or 'n/a'}",
        f"Technical sheet: {specs}",
        f"Requirement {req['requirement_id']}: {req['title']}",
        f"Instructions: {req['instructions']}",
        "Inspection points: " + "; ".join(req.get("inspection_points") or ["(see acceptance criteria)"]),
        "Acceptance criteria: " + "; ".join(req.get("acceptance_criteria") or ["(none listed)"]),
        "Possible findings to look for: " + "; ".join(req.get("possible_findings") or ["(none listed)"]),
        f"Required photo: {req.get('photo_guidance') or '(no specific guidance)'}",
        "Known limits of visual inspection for this requirement: "
        + "; ".join(req.get("visual_limitations") or ["(none listed)"]),
        f"Inspector note: {ctx.get('worker_note') or '(none)'}",
        f"Automated image checks (heuristic): {json.dumps(ctx.get('image_checks', {}))}",
        "Assess the attached photograph as evidence for this requirement.",
    ]
    return "\n".join(lines)


class NoProvider:
    name = "none"

    def available(self) -> tuple[bool, str]:
        return False, "AI assessment is disabled (AI_PROVIDER=none)."

    def assess(self, image_jpeg: bytes, context: dict[str, Any]) -> AssessmentOutcome:
        return AssessmentOutcome(self.name, None, "unavailable", None, self.available()[1], 0)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.model = settings.ai_model
        self._client = None

    def available(self) -> tuple[bool, str]:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "anthropic SDK not installed"
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE")):
            return False, "No Anthropic credentials configured (set ANTHROPIC_API_KEY in backend/.env)."
        return True, f"Claude ({self.model})"

    def _get_client(self):
        import anthropic
        if self._client is None:
            # Ignore ANTHROPIC_BASE_URL inherited from developer tooling; use AI_BASE_URL to override deliberately.
            self._client = anthropic.Anthropic(
                base_url=os.environ.get("AI_BASE_URL", "https://api.anthropic.com"),
                timeout=settings.ai_timeout_s, max_retries=settings.ai_max_retries)
        return self._client

    def assess(self, image_jpeg: bytes, context: dict[str, Any]) -> AssessmentOutcome:
        import anthropic
        ok, why = self.available()
        if not ok:
            return AssessmentOutcome(self.name, self.model, "unavailable", None, why, 0)
        started = time.monotonic()

        def done(status, result=None, error=None):
            return AssessmentOutcome(self.name, self.model, status, result, error,
                                     int((time.monotonic() - started) * 1000))

        kwargs: dict[str, Any] = {}
        if settings.ai_fallbacks:
            kwargs = {"extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                      "extra_body": {"fallbacks": "default"}}
        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                output_config={"effort": settings.ai_effort,
                               "format": {"type": "json_schema", "schema": ASSESSMENT_SCHEMA}},
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.standard_b64encode(image_jpeg).decode()}},
                    {"type": "text", "text": build_prompt(context)},
                ]}],
                **kwargs,
            )
        except anthropic.AuthenticationError:
            return done("failed", error="AI provider rejected the credentials.")
        except anthropic.RateLimitError:
            return done("failed", error="AI provider rate limit reached. Retry shortly.")
        except anthropic.APITimeoutError:
            return done("failed", error=f"AI assessment timed out after {settings.ai_timeout_s:.0f}s.")
        except anthropic.APIStatusError as exc:
            return done("failed", error=f"AI provider error ({exc.status_code}): {exc.message}"[:500])
        except anthropic.APIConnectionError:
            return done("failed", error="Could not reach the AI provider (network).")

        if response.stop_reason == "refusal":
            return done("refused", error="The AI model declined to assess this image.")
        if response.stop_reason == "max_tokens":
            return done("failed", error="AI response was truncated.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            return done("failed", error="AI returned no assessment.")
        try:
            result = AssessmentResult.model_validate(json.loads(text)).model_dump()
        except (json.JSONDecodeError, ValidationError) as exc:
            return done("failed", error=f"AI output failed schema validation: {exc}"[:500])
        return done("completed", result=result)


def get_provider() -> AssessmentProvider:
    if settings.ai_provider == "anthropic":
        return AnthropicProvider()
    return NoProvider()
