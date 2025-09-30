import subprocess
import json
from openai import OpenAI
import os
import time
import sys
import requests

# Initialize OpenAI client with DeepSeek-R1
client = OpenAI(
    api_key="8cAW1wtB6KyXcZ8GenYEu4Bfrz7DQvGA",
    base_url="https://ellm.nrp-nautilus.io/v1"
)

# Check if server is already running, otherwise start it
print("🔍 Checking if k8s-mcp-server is already running...")
server_process = None

try:
    response = requests.get("http://localhost:8080", timeout=1)
    print("✅ Server is already running on port 8080")
except:
    print("🚀 Starting k8s-mcp-server in SSE mode...")
    binary_name = 'k8s-mcp-server.exe' if sys.platform == 'win32' else 'k8s-mcp-server'
    binary_path = os.path.join(os.getcwd(), binary_name)

    server_process = subprocess.Popen(
        [binary_path, '--mode', 'sse', '--port', '8080'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, 'HOME': os.path.expanduser('~')}
    )

    # Wait for server to start
    print("⏳ Waiting for server to start...")
    time.sleep(3)

# Base URL for the MCP server
BASE_URL = "http://localhost:8080"

def call_k8s_tool(tool_name, arguments=None):
    """Call a k8s-mcp-server tool via HTTP and return the result"""
    if arguments is None:
        arguments = {}

    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    try:
        response = requests.post(
            f"{BASE_URL}/mcp",
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        result = response.json()

        if 'result' in result and 'content' in result['result']:
            return result['result']['content'][0]['text']
        elif 'error' in result:
            return f"Error: {result['error']['message']}"
        return str(result)
    except Exception as e:
        return f"Error calling tool: {e}"

def get_available_tools():
    """Get list of available k8s-mcp-server tools"""
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }

    try:
        response = requests.post(
            f"{BASE_URL}/mcp",
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        result = response.json()
        return result.get('result', {}).get('tools', [])
    except Exception as e:
        print(f"❌ Error getting tools: {e}")
        return []

# Get available tools
tools = get_available_tools()

if not tools:
    print("❌ Failed to connect to k8s-mcp-server.")
    server_process.terminate()
    sys.exit(1)

tool_descriptions = [{"name": t['name'], "description": t['description'], "inputSchema": t.get('inputSchema', {})} for t in tools]

print("\n" + "=" * 60)
print("💬 K8s Chat with DeepSeek-R1 + MCP Server")
print("=" * 60)
print(f"✅ Loaded {len(tools)} Kubernetes tools")
print("\n💡 Examples:")
print("  • List all pods in the gsoc namespace")
print("  • Show me the API resources")
print("  • Describe the xyz pod in gsoc namespace")
print("  • What deployments are running?")
print("\nType 'exit' or 'quit' to end the conversation\n")

# Chat loop with improved system prompt
conversation_history = [
    {
        "role": "system",
        "content": f"""You are an expert Kubernetes assistant with access to a real K8s cluster via MCP tools.

Available tools:
{json.dumps(tool_descriptions, indent=2)}

When users ask about Kubernetes resources:
1. Determine which tool(s) to use based on their question
2. Respond in this EXACT format:
   TOOL: <tool_name>
   ARGS: {{"param": "value"}}

3. After tool execution, interpret the results naturally for the user

Common patterns:
- "list/show pods" → listResources with Kind="Pod"
- "get api resources" → getAPIResources
- "describe <resource>" → describeResource with Kind, name, namespace
- "what namespaces" → listResources with Kind="Namespace"

If no tool is needed (general questions), respond conversationally."""
    }
]

try:
    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ['exit', 'quit', 'bye']:
            print("👋 Goodbye!")
            break

        conversation_history.append({
            "role": "user",
            "content": user_input
        })

        # Get AI response
        try:
            completion = client.chat.completions.create(
                model="deepseek-r1",
                messages=conversation_history,
                temperature=0.7
            )

            assistant_message = completion.choices[0].message.content

            # Check if assistant wants to use a tool
            if "TOOL:" in assistant_message and "ARGS:" in assistant_message:
                lines = assistant_message.split('\n')
                tool_name = None
                args_json = None

                for line in lines:
                    if line.strip().startswith("TOOL:"):
                        tool_name = line.replace("TOOL:", "").strip()
                    elif line.strip().startswith("ARGS:"):
                        args_json = line.replace("ARGS:", "").strip()

                if tool_name and args_json:
                    try:
                        args = json.loads(args_json)
                        print(f"\n🔧 Executing: {tool_name}({json.dumps(args)})")

                        result = call_k8s_tool(tool_name, args)

                        # Display results nicely
                        print("\n📋 Results:")
                        try:
                            result_data = json.loads(result)
                            if isinstance(result_data, list):
                                print(f"Found {len(result_data)} item(s):")
                                for item in result_data[:15]:
                                    if isinstance(item, dict):
                                        name = item.get('name', item.get('kind', 'Unknown'))
                                        namespace = item.get('namespace', '')
                                        if namespace:
                                            print(f"  • {name} (namespace: {namespace})")
                                        else:
                                            print(f"  • {name}")
                                    else:
                                        print(f"  • {item}")
                                if len(result_data) > 15:
                                    print(f"  ... and {len(result_data) - 15} more")
                            else:
                                print(json.dumps(result_data, indent=2))
                        except:
                            print(result[:1000])  # Show first 1000 chars if not JSON

                        # Add tool result to conversation for context
                        conversation_history.append({
                            "role": "assistant",
                            "content": f"Tool {tool_name} executed successfully. Result: {result[:500]}"
                        })

                        # Ask AI to interpret the results
                        conversation_history.append({
                            "role": "user",
                            "content": "Please summarize what we found in a natural way."
                        })

                        interpretation = client.chat.completions.create(
                            model="deepseek-r1",
                            messages=conversation_history,
                            temperature=0.7
                        )

                        interpretation_text = interpretation.choices[0].message.content
                        print(f"\n🤖 Assistant: {interpretation_text}\n")

                        conversation_history.append({
                            "role": "assistant",
                            "content": interpretation_text
                        })

                    except json.JSONDecodeError as e:
                        print(f"❌ Invalid JSON in args: {e}")
                    except Exception as e:
                        print(f"❌ Error executing tool: {e}")
            else:
                # Regular conversation response
                print(f"\n🤖 Assistant: {assistant_message}\n")
                conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message
                })

        except Exception as e:
            print(f"❌ Error: {e}\n")

except KeyboardInterrupt:
    print("\n\n👋 Goodbye!")

# Cleanup
if server_process:
    print("🧹 Cleaning up...")
    server_process.terminate()
    server_process.wait()