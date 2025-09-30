# K8s Chat Application

An interactive chat application that combines DeepSeek-R1 AI with Kubernetes MCP Server for natural language cluster management.

## Features

- 🤖 Natural language interaction with your Kubernetes cluster
- 💬 Powered by DeepSeek-R1 AI model
- 🔧 Direct integration with k8s-mcp-server
- 🚀 Auto-starts MCP server if not running
- 📊 Pretty-printed results
- 🔄 Maintains conversation context

## Prerequisites

- Go 1.21 or later (for building from source)
- Valid `~/.kube/config` file with cluster access
- Access to DeepSeek-R1 API endpoint

## Quick Start

### Option 1: Use Pre-built Binary

**Windows:**
```bash
./chat-app.exe
```

**Linux/Mac:**
```bash
./chat-app
```

### Option 2: Build from Source

```bash
go build -o chat-app.exe chat.go  # Windows
go build -o chat-app chat.go       # Linux/Mac
```

Then run the executable as shown above.

## Usage

Once started, you'll see:

```
🔍 Checking if k8s-mcp-server is already running...
✅ Server is already running on port 8080

============================================================
💬 K8s Chat with DeepSeek-R1 + MCP Server
============================================================
✅ Loaded 22 Kubernetes tools

💡 Examples:
  • List all pods in the gsoc namespace
  • Show me the API resources
  • Describe the xyz pod in gsoc namespace
  • What deployments are running?

Type 'exit' or 'quit' to end the conversation

You:
```

### Example Queries

**List resources:**
```
You: List all pods in the gsoc namespace
```

**Get cluster info:**
```
You: Show me all available API resources
```

**Describe resources:**
```
You: Describe the nginx pod in default namespace
```

**General questions:**
```
You: What deployments are running in my cluster?
```

**Exit the application:**
```
You: exit
```

## How It Works

1. **Server Check**: The app checks if k8s-mcp-server is running on port 8080
2. **Auto-Start**: If not running, it automatically starts the server in streamable-http mode
3. **AI Processing**: Your natural language query is sent to DeepSeek-R1
4. **Tool Selection**: AI determines which Kubernetes tool to use
5. **Execution**: The tool is executed via k8s-mcp-server
6. **Interpretation**: AI interprets the results and responds naturally

## Configuration

### API Endpoint

The DeepSeek-R1 endpoint is configured in `chat.go`:

```go
const (
    apiKey      = "your-api-key"
    baseURL     = "https://ellm.nrp-nautilus.io/v1"
    mcpServerURL = "http://localhost:8080"
)
```

### MCP Server Port

Default port is 8080. To change it, modify both:
- `mcpServerURL` constant in `chat.go`
- Server start command: `--port` flag

## Available Kubernetes Tools

The chat application has access to 22+ Kubernetes tools including:

- **Resource Management**: List, describe, get resources
- **API Discovery**: Get API resources, versions
- **Helm Operations**: List releases, get charts, history
- **Namespace Operations**: List, describe namespaces
- And more...

## Troubleshooting

### Server won't start

Ensure you have a valid kubeconfig:
```bash
# Check if config exists
ls ~/.kube/config

# On Windows, set HOME variable
$env:HOME = "C:\Users\YourUsername"
```

### Connection errors

Make sure k8s-mcp-server is running:
```bash
./k8s-mcp-server --mode streamable-http --port 8080
```

### API errors

Verify your API key and endpoint are correct in `chat.go`.

## Architecture

```
┌──────────────┐
│     User     │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│   Chat Application   │
│   (chat-app.exe)     │
└──────┬───────────────┘
       │
       ├─────────────────────┐
       │                     │
       ▼                     ▼
┌─────────────────┐   ┌──────────────────┐
│  DeepSeek-R1    │   │ k8s-mcp-server   │
│  (AI Model)     │   │  (Port 8080)     │
└─────────────────┘   └────────┬─────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │ Kubernetes API  │
                      └─────────────────┘
```

## Development

### Project Structure

```
chat.go          # Main chat application
chat.py          # Python version (alternative)
k8s-mcp-server   # MCP server binary
README.md        # k8s-mcp-server documentation
CHAT-README.md   # This file
```

### Adding Features

To modify the chat behavior, edit:
- System prompt in `main()` function
- Tool parsing logic in the main loop
- Display formatting in `displayResults()`

## License

Same as k8s-mcp-server project.

## Related

- [k8s-mcp-server README](README.md) - MCP server documentation
- [DeepSeek-R1](https://www.deepseek.com/) - AI model documentation
