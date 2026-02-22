#!/usr/bin/env python3
"""
LaTeX Renderer MCP Server

Converts LaTeX expressions into rendered PNG images and returns them
as base64-encoded data URIs. Designed to work with AI assistants like
Poke so math solutions can be sent as readable images via iMessage.
"""

import base64
import io
import json
import logging
import os
import re
import tempfile
from enum import Enum
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend, must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp.server.fastmcp import FastMCP

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Server ─────────────────────────────────────────────────────────────────────
mcp = FastMCP(
    "latex_mcp",
    instructions=(
        "Use render_latex to convert any LaTeX expression or full math solution "
        "into a PNG image. The tool returns a base64 PNG you can attach to messages. "
        "Always wrap math in proper LaTeX delimiters: $...$ for inline, $$...$$ for display."
    ),
)

# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_DPI = 150
DEFAULT_FONT_SIZE = 14
DEFAULT_BG_COLOR = "white"
DEFAULT_TEXT_COLOR = "black"
MAX_LATEX_LENGTH = 10_000


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _apply_theme(theme: Theme) -> tuple[str, str]:
    """Return (bg_color, text_color) for the given theme."""
    if theme == Theme.DARK:
        return "#1e1e2e", "#cdd6f4"
    return "white", "black"


def _strip_outer_delimiters(latex: str) -> str:
    """
    Remove surrounding $$ or $ if the whole string is wrapped in them.
    matplotlib's mathtext renderer expects raw LaTeX without outer $$.
    """
    latex = latex.strip()
    if latex.startswith("$$") and latex.endswith("$$"):
        return latex[2:-2].strip()
    if latex.startswith("$") and latex.endswith("$") and len(latex) > 2:
        return latex[1:-1].strip()
    return latex


def _render_latex_to_png(
    latex: str,
    dpi: int = DEFAULT_DPI,
    font_size: int = DEFAULT_FONT_SIZE,
    bg_color: str = DEFAULT_BG_COLOR,
    text_color: str = DEFAULT_TEXT_COLOR,
    padding: float = 0.3,
) -> bytes:
    """
    Render a LaTeX string to PNG bytes using matplotlib's mathtext engine.
    Supports inline math, display math, multi-line solutions, and plain text.
    """
    # Split into lines so we can render multi-step solutions
    lines = latex.strip().split("\n")

    fig = plt.figure(facecolor=bg_color)
    fig.set_facecolor(bg_color)

    # Build a single text block — join lines with newlines for matplotlib
    rendered_text = "\n".join(
        f"${_strip_outer_delimiters(line.strip())}$" if line.strip() and not line.strip().startswith("#") else line
        for line in lines
    )

    # Render off-screen to measure size, then resize figure
    text_obj = fig.text(
        0.5, 0.5,
        rendered_text,
        ha="center", va="center",
        fontsize=font_size,
        color=text_color,
        usetex=False,  # Use matplotlib mathtext, no LaTeX installation needed
        wrap=True,
    )

    # Auto-size figure to content
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=bg_color, pad_inches=padding)
    plt.close(fig)

    buf.seek(0)
    return buf.read()


def _render_multiblock(
    blocks: list[dict],
    dpi: int = DEFAULT_DPI,
    font_size: int = DEFAULT_FONT_SIZE,
    bg_color: str = DEFAULT_BG_COLOR,
    text_color: str = DEFAULT_TEXT_COLOR,
) -> bytes:
    """
    Render a structured solution with labeled steps:
    blocks = [{"label": "Step 1", "latex": "..."}, ...]
    """
    n = len(blocks)
    fig, axes = plt.subplots(n, 1, figsize=(8, 2.5 * n), facecolor=bg_color)
    if n == 1:
        axes = [axes]

    for ax, block in zip(axes, blocks):
        ax.set_facecolor(bg_color)
        ax.axis("off")
        label = block.get("label", "")
        latex = block.get("latex", "")
        stripped = _strip_outer_delimiters(latex)

        full_text = f"\\mathbf{{{label}}}\n${stripped}$" if label else f"${stripped}$"
        ax.text(
            0.5, 0.5, full_text,
            ha="center", va="center",
            fontsize=font_size,
            color=text_color,
            transform=ax.transAxes,
            usetex=False,
        )

    plt.tight_layout(pad=1.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=bg_color)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _png_to_base64_uri(png_bytes: bytes) -> str:
    """Convert PNG bytes to a data URI string."""
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _png_to_base64(png_bytes: bytes) -> str:
    """Return raw base64 string (no data URI prefix)."""
    return base64.b64encode(png_bytes).decode("utf-8")


# ── Input Models ───────────────────────────────────────────────────────────────

class RenderLatexInput(BaseModel):
    """Input model for rendering a LaTeX expression to a PNG image."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    latex: str = Field(
        ...,
        description=(
            "LaTeX expression to render. Can include math delimiters ($, $$) or raw LaTeX. "
            "Multi-line solutions supported — separate steps with newlines. "
            "Example: '$$x = \\\\frac{-b \\\\pm \\\\sqrt{b^2-4ac}}{2a}$$'"
        ),
        min_length=1,
        max_length=MAX_LATEX_LENGTH,
    )
    theme: Theme = Field(
        default=Theme.LIGHT,
        description="Color theme: 'light' (white bg, black text) or 'dark' (dark bg, light text).",
    )
    dpi: int = Field(
        default=DEFAULT_DPI,
        description="Image resolution in DPI. Higher = sharper but larger file. Range: 72–300.",
        ge=72,
        le=300,
    )
    font_size: int = Field(
        default=DEFAULT_FONT_SIZE,
        description="Font size for rendered math. Range: 8–32.",
        ge=8,
        le=32,
    )

    @field_validator("latex")
    @classmethod
    def validate_latex(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("LaTeX expression cannot be empty or whitespace only.")
        return v


class RenderSolutionInput(BaseModel):
    """Input model for rendering a full multi-step math solution."""
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    steps: list[dict] = Field(
        ...,
        description=(
            "List of solution steps, each with 'label' and 'latex' keys. "
            "Example: [{\"label\": \"Given\", \"latex\": \"ax^2+bx+c=0\"}, "
            "{\"label\": \"Solve\", \"latex\": \"x=\\\\frac{-b\\\\pm\\\\sqrt{b^2-4ac}}{2a}\"}]"
        ),
        min_length=1,
        max_length=20,
    )
    theme: Theme = Field(default=Theme.LIGHT, description="Color theme: 'light' or 'dark'.")
    dpi: int = Field(default=DEFAULT_DPI, description="Image resolution (72–300 DPI).", ge=72, le=300)
    font_size: int = Field(default=DEFAULT_FONT_SIZE, description="Font size (8–32).", ge=8, le=32)

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v: list) -> list:
        for i, step in enumerate(v):
            if not isinstance(step, dict):
                raise ValueError(f"Step {i} must be a dict with 'label' and 'latex' keys.")
            if "latex" not in step:
                raise ValueError(f"Step {i} is missing required 'latex' key.")
        return v


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool(
    name="render_latex",
    annotations={
        "title": "Render LaTeX to Image",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def render_latex(params: RenderLatexInput) -> str:
    """
    Render a LaTeX math expression into a PNG image and return it as a base64 data URI.

    Use this tool whenever you solve a math problem and want to present the answer
    or working in a clean, readable image format — perfect for sending via iMessage
    or any messaging platform.

    Supports:
    - Single expressions: $E = mc^2$
    - Display math: $$\\int_0^\\infty e^{-x} dx = 1$$
    - Multi-line solutions (separate steps with newlines)
    - Greek letters, fractions, integrals, sums, matrices, etc.

    Args:
        params (RenderLatexInput): Validated input containing:
            - latex (str): The LaTeX expression(s) to render
            - theme (str): 'light' or 'dark' color scheme
            - dpi (int): Image resolution (default 150)
            - font_size (int): Text size (default 14)

    Returns:
        str: JSON with keys:
            - success (bool): Whether rendering succeeded
            - data_uri (str): Base64 PNG as data:image/png;base64,... URI
            - base64 (str): Raw base64 PNG string
            - width_hint (str): Suggested display width
            - message (str): Human-readable status or error
    """
    try:
        bg_color, text_color = _apply_theme(params.theme)
        logger.info("Rendering LaTeX (len=%d, theme=%s, dpi=%d)", len(params.latex), params.theme, params.dpi)

        png_bytes = _render_latex_to_png(
            latex=params.latex,
            dpi=params.dpi,
            font_size=params.font_size,
            bg_color=bg_color,
            text_color=text_color,
        )

        data_uri = _png_to_base64_uri(png_bytes)
        b64 = _png_to_base64(png_bytes)
        size_kb = len(png_bytes) / 1024

        logger.info("Rendered successfully: %.1f KB", size_kb)
        return json.dumps({
            "success": True,
            "data_uri": data_uri,
            "base64": b64,
            "width_hint": "600px",
            "size_kb": round(size_kb, 1),
            "message": f"LaTeX rendered successfully ({size_kb:.1f} KB PNG). "
                       "Use 'data_uri' to embed in HTML or 'base64' to attach as image.",
        })

    except Exception as e:
        logger.error("Render failed: %s", e)
        return json.dumps({
            "success": False,
            "data_uri": None,
            "base64": None,
            "message": (
                f"Rendering failed: {str(e)}. "
                "Check that your LaTeX syntax is valid. "
                "Note: this server uses matplotlib mathtext — most standard LaTeX math is supported, "
                "but some advanced packages (tikz, chemfig) are not."
            ),
        })


@mcp.tool(
    name="render_solution",
    annotations={
        "title": "Render Full Math Solution",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def render_solution(params: RenderSolutionInput) -> str:
    """
    Render a complete multi-step math solution as a single stacked PNG image.

    Use this when you've solved a math problem step-by-step and want to present
    the full working clearly — each step gets its own labeled row in the image.

    Example input:
    {
        "steps": [
            {"label": "Problem", "latex": "Solve: x^2 - 5x + 6 = 0"},
            {"label": "Factor",  "latex": "(x-2)(x-3) = 0"},
            {"label": "Answer",  "latex": "x = 2 \\\\text{ or } x = 3"}
        ]
    }

    Args:
        params (RenderSolutionInput): Validated input containing:
            - steps (list[dict]): List of {label, latex} dicts (max 20 steps)
            - theme (str): 'light' or 'dark'
            - dpi (int): Resolution (default 150)
            - font_size (int): Text size (default 14)

    Returns:
        str: JSON with keys:
            - success (bool)
            - data_uri (str): Base64 PNG data URI
            - base64 (str): Raw base64
            - step_count (int): Number of steps rendered
            - message (str): Status or error detail
    """
    try:
        bg_color, text_color = _apply_theme(params.theme)
        logger.info("Rendering solution with %d steps", len(params.steps))

        png_bytes = _render_multiblock(
            blocks=params.steps,
            dpi=params.dpi,
            font_size=params.font_size,
            bg_color=bg_color,
            text_color=text_color,
        )

        data_uri = _png_to_base64_uri(png_bytes)
        b64 = _png_to_base64(png_bytes)
        size_kb = len(png_bytes) / 1024

        logger.info("Solution rendered: %d steps, %.1f KB", len(params.steps), size_kb)
        return json.dumps({
            "success": True,
            "data_uri": data_uri,
            "base64": b64,
            "step_count": len(params.steps),
            "size_kb": round(size_kb, 1),
            "message": f"Solution with {len(params.steps)} steps rendered ({size_kb:.1f} KB). "
                       "Send the base64 PNG as an image attachment.",
        })

    except Exception as e:
        logger.error("Solution render failed: %s", e)
        return json.dumps({
            "success": False,
            "data_uri": None,
            "base64": None,
            "step_count": 0,
            "message": f"Rendering failed: {str(e)}. Verify each step has a valid 'latex' field.",
        })


@mcp.tool(
    name="check_latex_syntax",
    annotations={
        "title": "Check LaTeX Syntax",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def check_latex_syntax(latex: str) -> str:
    """
    Validate LaTeX syntax by attempting a dry-run render.

    Use this before calling render_latex if you're unsure whether the expression
    is valid. Returns a list of potential issues and whether rendering is likely to succeed.

    Args:
        latex (str): LaTeX expression to validate (max 10,000 chars).

    Returns:
        str: JSON with keys:
            - valid (bool): Whether the expression appears renderable
            - warnings (list[str]): Non-fatal issues detected
            - errors (list[str]): Fatal issues that will prevent rendering
            - suggestion (str): Corrected LaTeX if a common fix is available
    """
    warnings = []
    errors = []
    suggestion = None

    if not latex or not latex.strip():
        return json.dumps({"valid": False, "warnings": [], "errors": ["Empty expression."], "suggestion": None})

    if len(latex) > MAX_LATEX_LENGTH:
        errors.append(f"Expression too long ({len(latex)} chars, max {MAX_LATEX_LENGTH}).")

    # Check unbalanced delimiters
    dollar_count = latex.count("$")
    if dollar_count % 2 != 0:
        errors.append("Unbalanced $ delimiters — ensure math is wrapped in matching $ or $$.")

    # Check for common unsupported environments
    unsupported = ["\\begin{tikzpicture}", "\\usepackage", "\\documentclass", "\\chemfig"]
    for env in unsupported:
        if env in latex:
            errors.append(f"'{env}' is not supported by matplotlib mathtext. Use standard math LaTeX only.")

    # Check for common fixes
    if "\\frac" in latex and "{" not in latex:
        warnings.append("\\frac requires two arguments in braces: \\frac{numerator}{denominator}")

    if re.search(r"\\(alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|omega)\b", latex):
        pass  # These are fine
    elif "\\" in latex and not any(cmd in latex for cmd in ["\\frac", "\\sqrt", "\\int", "\\sum", "\\prod", "\\lim", "\\text"]):
        warnings.append("Backslash detected but no recognized LaTeX commands found. Verify command names.")

    # Try actual render
    try:
        _render_latex_to_png(latex, dpi=72, font_size=12)
        valid = len(errors) == 0
    except Exception as e:
        errors.append(f"Render test failed: {str(e)}")
        valid = False

    return json.dumps({
        "valid": valid,
        "warnings": warnings,
        "errors": errors,
        "suggestion": suggestion,
    })


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    logger.info("Starting latex_mcp server | transport=%s host=%s port=%d", transport, host, port)

    if transport == "streamable-http":
        mcp.run(transport="streamable-http", host=host, port=port)
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
