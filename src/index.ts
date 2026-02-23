import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export interface Env {}

// CodeCogs renders LaTeX to PNG — works headless, no native deps needed
const CODECOGS_BASE = "https://latex.codecogs.com/png.image";

function buildCodeCogsUrl(latex: string, dpi: number = 200, color: string = "white"): string {
  // CodeCogs format: \dpi{200}\color{white} <latex>
  const prefix = `\\dpi{${dpi}}\\color{${color}}`;
  const encoded = encodeURIComponent(`${prefix} ${latex}`);
  return `${CODECOGS_BASE}?${encoded}`;
}

async function fetchImageAsBase64(url: string): Promise<{ data: string; mimeType: string }> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch image: ${res.status}`);
  const buffer = await res.arrayBuffer();
  const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
  return { data: base64, mimeType: "image/png" };
}

// Build a simple step-by-step solution as a single LaTeX expression
function buildSolutionLatex(steps: string[], answer: string): string {
  const stepLines = steps.map((s, i) =>
    steps.length > 1 ? `\\text{Step ${i + 1}: } & ${s} \\\\` : `\\text{Work: } & ${s} \\\\`
  );
  return [
    "\\begin{array}{rl}",
    ...stepLines,
    `\\textbf{Answer: } & \\boldsymbol{${answer}}`,
    "\\end{array}",
  ].join(" ");
}

// ---------------------------------------------------------------------------
// MCP Agent
// ---------------------------------------------------------------------------
export class LatexMCP extends McpAgent<Env> {
  server = new McpServer({ name: "latex-mcp", version: "1.0.0" });

  async init() {

    // -----------------------------------------------------------------------
    // 1. render_latex
    // -----------------------------------------------------------------------
    this.server.tool(
      "render_latex",
      "Render a single LaTeX expression and return it as a PNG image. Do NOT wrap latex in dollar signs.",
      {
        latex: z.string().describe("LaTeX expression e.g. 'x^2 + y^2 = z^2'. No $ delimiters."),
        font_size: z.number().optional().default(18).describe("Font size / DPI scale (default 18 → 150 dpi)"),
        bg_color: z.string().optional().default("white").describe("Background color (default 'white')"),
        text_color: z.string().optional().default("black").describe("Equation color (default 'black')"),
      },
      async ({ latex, font_size, bg_color, text_color }) => {
        const dpi = Math.round((font_size ?? 18) * 10);
        const url = buildCodeCogsUrl(latex, dpi, text_color ?? "black");
        try {
          const { data, mimeType } = await fetchImageAsBase64(url);
          return { content: [{ type: "image", data, mimeType }] };
        } catch {
          // Fallback: return the URL so the client can render it
          return { content: [{ type: "text", text: `Image URL: ${url}` }] };
        }
      }
    );

    // -----------------------------------------------------------------------
    // 2. render_solution
    // -----------------------------------------------------------------------
    this.server.tool(
      "render_solution",
      "Render a complete step-by-step math solution as a PNG image. PRIMARY tool to call after solving any math problem. Do NOT wrap any LaTeX strings in dollar signs.",
      {
        problem_description: z.string().describe("Plain-English problem e.g. 'Solve for x: 2x + 4 = 10'"),
        steps_latex: z.array(z.string()).describe("LaTeX for each step e.g. ['2x+4=10', '2x=6', 'x=3']"),
        final_answer_latex: z.string().describe("LaTeX for the final answer only e.g. 'x = 3'"),
        dpi: z.number().optional().default(200).describe("Image resolution (default 200)"),
      },
      async ({ steps_latex, final_answer_latex, dpi }) => {
        const solutionLatex = buildSolutionLatex(steps_latex, final_answer_latex);
        const url = buildCodeCogsUrl(solutionLatex, dpi ?? 200, "black");
        try {
          const { data, mimeType } = await fetchImageAsBase64(url);
          return { content: [{ type: "image", data, mimeType }] };
        } catch {
          return { content: [{ type: "text", text: `Image URL: ${url}` }] };
        }
      }
    );

    // -----------------------------------------------------------------------
    // 3. get_image_url
    // -----------------------------------------------------------------------
    this.server.tool(
      "get_image_url",
      "Returns a hosted CodeCogs URL for any LaTeX expression — iOS renders it inline in iMessage.",
      {
        latex: z.string().describe("LaTeX expression. No $ delimiters."),
        dpi: z.number().optional().default(200).describe("Resolution (default 200)"),
        color: z.string().optional().default("black").describe("Text color (default 'black')"),
      },
      async ({ latex, dpi, color }) => {
        const url = buildCodeCogsUrl(latex, dpi ?? 200, color ?? "black");
        return { content: [{ type: "text", text: url }] };
      }
    );
  }
}

// ---------------------------------------------------------------------------
// Worker entry point
// ---------------------------------------------------------------------------
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return new Response("OK", { status: 200 });
    }

    return LatexMCP.serve("/mcp").fetch(request, env, ctx);
  },
};
