# latex-mcp 🧮

An MCP server that converts LaTeX math expressions into clean PNG images.

Built for use with AI assistants like **Poke** — when the AI solves a math problem,
it calls this server to render the solution as a beautiful image, then sends it back
via iMessage or any messaging platform.

## Tools

### `render_latex`
Render a single LaTeX expression to a PNG image.

```json
{
  "latex": "$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$",
  "theme": "light",
  "dpi": 150
}
```

Returns `data_uri` (embed in HTML) and `base64` (attach as image).

### `render_solution`
Render a full multi-step solution as a stacked image.

```json
{
  "steps": [
    {"label": "Problem", "latex": "x^2 - 5x + 6 = 0"},
    {"label": "Factor",  "latex": "(x-2)(x-3) = 0"},
    {"label": "Answer",  "latex": "x = 2 \\text{ or } x = 3"}
  ]
}
```

### `check_latex_syntax`
Validate LaTeX before rendering — returns warnings and errors.

## MCP Endpoint

```
https://latex-mcp.onrender.com/mcp
```

## Add to Poke / Claude Desktop

```json
{
  "mcpServers": {
    "latex-mcp": {
      "command": "npx",
      "args": ["mcp-remote", "https://latex-mcp.onrender.com/mcp"]
    }
  }
}
```

## Local Development

```bash
pip install fastmcp matplotlib pydantic
MCP_TRANSPORT=streamable-http python3 -m src.server
```
