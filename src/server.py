import base64
import io
import json
import logging
import os
import urllib.parse
import urllib.request

import matplotlib
import matplotlib.pyplot as plt
from fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

matplotlib.use("Agg")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="latex_mcp",
    instructions=(
        "Renders LaTeX math expressions into PNG images. "
        "Use render_solution after solving a math problem to return a beautiful image. "
        "Use get_image_url for a shareable URL (best for iMessage). "
        "Use render_latex for a raw base64 PNG."
    ),
)

DEFAULT_FONT_SIZE = 18
DEFAULT_DPI = 180
CODECOGS_BASE = "https://latex.codecogs.com/png.image"


class RenderLatexInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    latex: str = Field(..., description="LaTeX expression to render. Do NOT wrap in $...$ delimiters.", min_length=1, max_length=4000)
    font_size: Optional[int] = Field(default=DEFAULT_FONT_SIZE, description="Font size in points (default 18, range 8-48).", ge=8, le=48)
    dpi: Optional[int] = Field(default=DEFAULT_DPI, description="Image DPI (default 180, range 72-600).", ge=72, le=600)
    bg_color: Optional[str] = Field(default="white", description="Background: 'white' or 'transparent'.")
    text_color: Optional[str] = Field(default="black", description="Equation color (default 'black').")
    padding: Optional[float] = Field(default=0.3, description="Padding in inches (default 0.3).", ge=0.0, le=2.0)


class GetImageUrlInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    latex: str = Field(..., description="LaTeX expression. Do NOT wrap in $...$ delimiters.", min_length=1, max_length=2000)
    style: Optional[str] = Field(default=r"\dpi{180}\bg{white}\color{black}", description="CodeCogs style prefix.")


def _render_to_png_bytes(latex: str, font_size: int, dpi: int, bg_color: str, text_color: str, padding: float) -> bytes:
    expression = f"${latex}$"
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.patch.set_facecolor("none" if bg_color == "transparent" else bg_color)
    text_obj = fig.text(0, 0, expression, fontsize=font_size, color=text_color, usetex=False)
    renderer = fig.canvas.get_renderer()
    bbox = text_obj.get_window_extent(renderer=renderer)
    pad_px = padding * dpi
    width_in = (bbox.width + 2 * pad_px) / dpi
    height_in = (bbox.height + 2 * pad_px) / dpi
    fig.set_size_inches(max(width_in, 1.0), max(height_in, 0.5))
    text_obj.set_position((pad_px / (fig.get_figwidth() * dpi), pad_px / (fig.get_figheight() * dpi)))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", transparent=(bg_color == "transparent"), pad_inches=padding)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _build_codecogs_url(latex: str, style: str) -> str:
    styled = f"{style}?{latex}"
    encoded = urllib.parse.quote(styled, safe=r"\{}[]()^_.*+-=/<>|!@#%&,;:'\"")
    return f"{CODECOGS_BASE}/{encoded}"


@mcp.tool(
    name="render_latex",
    annotations={"title": "Render LaTeX to PNG", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def render_latex(params: RenderLatexInput) -> str:
    """Render a LaTeX expression and return a base64-encoded PNG image.

    Call this when you want to show a math equation as a clean image.
    Returns base64 PNG data and a data URI that can be embedded directly.

    Args:
        params (RenderLatexInput): latex, font_size, dpi, bg_color, text_color, padding

    Returns:
        str: JSON with base64_png, data_uri, latex, size_kb, success
    """
    try:
        logger.info(f"Rendering LaTeX: {params.latex[:80]}")
        png_bytes = _render_to_png_bytes(
            params.latex,
            params.font_size or DEFAULT_FONT_SIZE,
            params.dpi or DEFAULT_DPI,
            params.bg_color or "white",
            params.text_color or "black",
            params.padding if params.padding is not None else 0.3,
        )
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        return json.dumps({
            "success": True,
            "base64_png": b64,
            "data_uri": f"data:image/png;base64,{b64}",
            "latex": params.latex,
            "size_kb": round(len(png_bytes) / 1024, 1),
        })
    except Exception as e:
        logger.error(f"render_latex failed: {e}")
        return json.dumps({"success": False, "error": str(e), "hint": "Check LaTeX syntax — unmatched braces are common."})


@mcp.tool(
    name="get_image_url",
    annotations={"title": "Get Hosted LaTeX Image URL", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def get_image_url(params: GetImageUrlInput) -> str:
    """Get a publicly-hosted URL for a rendered LaTeX image via CodeCogs.

    Best tool for iMessage sharing. The URL points to a live-rendered PNG
    that iOS will display inline when sent as a message.

    Args:
        params (GetImageUrlInput): latex, style

    Returns:
        str: JSON with image_url, latex, url_reachable, instructions
    """
    try:
        url = _build_codecogs_url(params.latex, params.style or r"\dpi{180}\bg{white}\color{black}")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=5):
                reachable = True
        except Exception:
            reachable = False
        return json.dumps({
            "success": True,
            "image_url": url,
            "latex": params.latex,
            "url_reachable": reachable,
            "instructions": "Send this URL in iMessage — iOS renders it as an inline image automatically.",
        })
    except Exception as e:
        logger.error(f"get_image_url failed: {e}")
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool(
    name="render_solution",
    annotations={"title": "Render Full Math Solution", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def render_solution(
    problem_description: str,
    steps_latex: list[str],
    final_answer_latex: str,
    font_size: int = 16,
    dpi: int = 180,
) -> str:
    """Render a complete step-by-step math solution as a PNG image with a hosted URL.

    PRIMARY tool to call after solving a math problem from a photo.
    Renders each solution step and the final answer into one clean image.
    Returns both a base64 PNG (full steps) and a hosted URL (final answer, best for iMessage).

    Args:
        problem_description (str): Plain-English description of the problem
        steps_latex (list[str]): LaTeX strings for each step. E.g. ["2x+4=10", "2x=6", "x=3"]
        final_answer_latex (str): LaTeX for the final answer only. E.g. "x=3"
        font_size (int): Font size in points (default 16)
        dpi (int): Image DPI (default 180)

    Returns:
        str: JSON with image_url (hosted, for iMessage), base64_png (full steps),
             data_uri, steps_count, final_answer, size_kb, message
    """
    try:
        logger.info(f"Rendering solution with {len(steps_latex)} steps")
        n_rows = len(steps_latex) + 1
        fig_height = max(1.5, n_rows * 1.0 + 0.6)
        fig, axes = plt.subplots(n_rows, 1, figsize=(8, fig_height))
        fig.patch.set_facecolor("white")
        if n_rows == 1:
            axes = [axes]

        for i, (ax, step) in enumerate(zip(axes[:-1], steps_latex)):
            ax.axis("off")
            ax.set_facecolor("white")
            label = f"Step {i + 1}:" if len(steps_latex) > 1 else "Solution:"
            ax.text(0.02, 0.5, label, transform=ax.transAxes, fontsize=font_size - 2,
                    color="#555555", va="center", fontweight="bold")
            ax.text(0.22, 0.5, f"${step}$", transform=ax.transAxes, fontsize=font_size,
                    color="black", va="center")

        ans_ax = axes[-1]
        ans_ax.axis("off")
        ans_ax.set_facecolor("#eef4ff")
        ans_ax.text(0.02, 0.5, "Answer:", transform=ans_ax.transAxes, fontsize=font_size,
                    color="#003399", va="center", fontweight="bold")
        ans_ax.text(0.22, 0.5, f"${final_answer_latex}$", transform=ans_ax.transAxes,
                    fontsize=font_size + 2, color="#003399", va="center", fontweight="bold")

        fig.suptitle(problem_description, fontsize=font_size - 2, color="#333333", y=1.01, style="italic")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", pad_inches=0.25)
        plt.close(fig)
        buf.seek(0)
        png_bytes = buf.read()

        b64 = base64.b64encode(png_bytes).decode("utf-8")
        hosted_url = _build_codecogs_url(final_answer_latex, r"\dpi{200}\bg{white}\color{black}")

        return json.dumps({
            "success": True,
            "image_url": hosted_url,
            "base64_png": b64,
            "data_uri": f"data:image/png;base64,{b64}",
            "steps_count": len(steps_latex),
            "final_answer": final_answer_latex,
            "size_kb": round(len(png_bytes) / 1024, 1),
            "message": (
                f"Rendered {len(steps_latex)} step(s) successfully. "
                "Send image_url in iMessage to show the answer as an inline image."
            ),
        })
    except Exception as e:
        logger.error(f"render_solution failed: {e}")
        return json.dumps({"success": False, "error": str(e), "hint": "Check all LaTeX in steps_latex and final_answer_latex."})


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting latex_mcp | transport={transport} | {host}:{port}")
    if transport == "streamable-http":
        mcp.run(transport="streamable-http", host=host, port=port)
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
