# latex-mcp 🧮

An MCP server that renders LaTeX math expressions into beautiful PNG images — built for AI assistants like Poke that solve math problems from photos.

## How It Works

```
User sends photo of math problem
→ AI (Poke) solves it
→ AI calls this MCP server with the LaTeX solution
→ Server renders it into a clean PNG image
→ AI sends the image URL back in iMessage
```

## Tools

### `render_solution` ⭐ (Primary tool)
Renders a full step-by-step solution with highlighted final answer.
Returns both a hosted image URL (for iMessage) and a base64 PNG.

### `get_image_url`
Returns a hosted CodeCogs URL for any LaTeX expression — iOS renders it inline in iMessage.

### `render_latex`
Renders LaTeX to a base64-encoded PNG for embedding.

## MCP Endpoint

```
https://latex-mcp.onrender.com/mcp
```

## Connect to Poke / Claude Desktop

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

## Example Usage

When Poke solves `2x + 4 = 10`, it should call:

```json
{
  "tool": "render_solution",
  "params": {
    "problem_description": "Solve for x: 2x + 4 = 10",
    "steps_latex": ["2x + 4 = 10", "2x = 10 - 4", "2x = 6", "x = \\frac{6}{2}"],
    "final_answer_latex": "x = 3"
  }
}
```

Returns an `image_url` to send directly in iMessage. 🎉
