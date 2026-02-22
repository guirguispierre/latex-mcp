import base64
import io
import json
import logging
import os

import matplotlib
import matplotlib.pyplot as plt
import uvicorn
from fastmcp import FastMCP
from matplotlib import rcParams

matplotlib.use("Agg")

# Use a font that supports math symbols well
rcParams['mathtext.fontset'] = 'cm'
rcParams['font.family'] = 'serif'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="latex_mcp",
    instructions=(
        "Renders LaTeX math expressions into PNG images. "
        "Use render_solution after solving a math problem — it returns a base64 PNG "
        "and a data_uri you can embed directly. "
        "Always present the image to the user so they can see the rendered math."
    ),
)


def _render_expression(latex: str, font_size: int = 18, dpi: int = 200,
                        bg_color: str = "white", text_color: str = "black",
                        padding: float = 0.25) -> bytes:
    """Render a single LaTeX expression to PNG bytes using matplotlib mathtext."""
    expr = rf"${latex}$"
    fig = plt.figure(facecolor=bg_color)
    fig.set_size_inches(0.01, 0.01)  # will be resized
    t = fig.text(0.5, 0.5, expr, fontsize=font_size, color=text_color,
                 ha="center", va="center", usetex=False)
    # Render once to measure
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                pad_inches=padding, facecolor=bg_color)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _render_steps_image(problem: str, steps: list[str], answer: str,
                         font_size: int = 15, dpi: int = 200) -> bytes:
    """Render a full step-by-step solution to PNG bytes."""
    n = len(steps) + 1  # steps + answer row
    row_h = 0.85
    fig_h = max(2.0, n * row_h + 0.8)

    fig, axes = plt.subplots(n, 1, figsize=(9, fig_h), facecolor="white")
    if n == 1:
        axes = [axes]

    fig.suptitle(problem, fontsize=font_size - 2, color="#333333",
                 style="italic", y=1.0)

    # Step rows
    for i, (ax, step) in enumerate(zip(axes[:-1], steps)):
        ax.set_facecolor("#f9f9f9" if i % 2 == 0 else "white")
        ax.axis("off")
        label = f"Step {i + 1}:" if len(steps) > 1 else "Work:"
        ax.text(0.02, 0.5, label, transform=ax.transAxes,
                fontsize=font_size - 3, color="#666666",
                va="center", fontweight="bold")
        ax.text(0.18, 0.5, rf"${step}$", transform=ax.transAxes,
                fontsize=font_size, color="#111111", va="center",
                usetex=False)

    # Answer row — highlighted blue
    ans_ax = axes[-1]
    ans_ax.set_facecolor("#dbeafe")
    ans_ax.axis("off")
    ans_ax.text(0.02, 0.5, "Answer:", transform=ans_ax.transAxes,
                fontsize=font_size - 1, color="#1d4ed8",
                va="center", fontweight="bold")
    ans_ax.text(0.18, 0.5, rf"${answer}$", transform=ans_ax.transAxes,
                fontsize=font_size + 2, color="#1d4ed8",
                va="center", fontweight="bold", usetex=False)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", pad_inches=0.2)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


@mcp.tool(
    name="render_latex",
    annotations={"title": "Render LaTeX to PNG", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def render_latex(
    latex: str,
    font_size: int = 18,
    dpi: int = 200,
    bg_color: str = "white",
    text_color: str = "black",
    padding: float = 0.25,
) -> str:
    """Render a single LaTeX expression and return a base64 PNG image.

    Do NOT wrap latex in dollar signs — the server adds them automatically.
    Returns base64_png and data_uri for embedding the image directly.

    Args:
        latex: LaTeX expression e.g. 'x^2 + y^2 = z^2'. No $ delimiters.
        font_size: Font size in points (default 18).
        dpi: Image resolution (default 200).
        bg_color: Background color — 'white' or 'transparent'.
        text_color: Text/equation color (default 'black').
        padding: Padding in inches around the equation (default 0.25).

    Returns:
        JSON with: success, base64_png, data_uri, latex, size_kb
    """
    try:
        logger.info(f"render_latex: {latex[:80]}")
        png = _render_expression(latex, font_size, dpi, bg_color, text_color, padding)
        b64 = base64.b64encode(png).decode()
        return json.dumps({
            "success": True,
            "base64_png": b64,
            "data_uri": f"data:image/png;base64,{b64}",
            "latex": latex,
            "size_kb": round(len(png) / 1024, 1),
        })
    except Exception as e:
        logger.error(f"render_latex error: {e}")
        return json.dumps({"success": False, "error": str(e),
                           "hint": "Check LaTeX syntax. Common issues: unmatched braces, invalid commands."})


@mcp.tool(
    name="render_solution",
    annotations={"title": "Render Full Math Solution", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def render_solution(
    problem_description: str,
    steps_latex: list[str],
    final_answer_latex: str,
    font_size: int = 15,
    dpi: int = 200,
) -> str:
    """Render a complete step-by-step math solution as a single PNG image.

    PRIMARY tool to call after solving any math problem from a photo.
    Renders each solution step and the final answer into one clean,
    easy-to-read image with a blue highlighted answer row.

    Do NOT wrap any LaTeX strings in dollar signs.

    Args:
        problem_description: Plain-English problem e.g. 'Solve for x: 2x + 4 = 10'
        steps_latex: LaTeX for each step e.g. ['2x+4=10', '2x=6', 'x=3']
        final_answer_latex: LaTeX for the final answer only e.g. 'x = 3'
        font_size: Font size in points (default 15).
        dpi: Image resolution (default 200).

    Returns:
        JSON with: success, base64_png, data_uri, steps_count, final_answer, size_kb, message
    """
    try:
        logger.info(f"render_solution: '{problem_description}' — {len(steps_latex)} steps")
        png = _render_steps_image(problem_description, steps_latex, final_answer_latex,
                                   font_size, dpi)
        b64 = base64.b64encode(png).decode()
        return json.dumps({
            "success": True,
            "base64_png": b64,
            "data_uri": f"data:image/png;base64,{b64}",
            "steps_count": len(steps_latex),
            "final_answer": final_answer_latex,
            "size_kb": round(len(png) / 1024, 1),
            "message": (
                f"Solution image rendered with {len(steps_latex)} step(s). "
                "Display the base64_png or data_uri as an image for the user."
            ),
        })
    except Exception as e:
        logger.error(f"render_solution error: {e}")
        return json.dumps({"success": False, "error": str(e),
                           "hint": "Check all LaTeX in steps_latex and final_answer_latex."})


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting latex_mcp | transport={transport} | {host}:{port}")

    if transport in ("streamable-http", "sse"):
        app = mcp.http_app(transport=transport)
        uvicorn.run(app, host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
