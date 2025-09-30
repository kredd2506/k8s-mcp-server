import subprocess
import json
from openai import OpenAI
import sys
import os

# Initialize OpenAI client
client = OpenAI(
    api_key="8cAW1wtB6KyXcZ8GenYEu4Bfrz7DQvGA",
    base_url="https://ellm.nrp-nautilus.io/"
)

# Start k8s-mcp-server in stdio mode
print("Starting k8s-mcp-server...")

# Use the full path to the binary
binary_path = os.path.join(os.getcwd(), 'k8s-mcp-server')

server_process = subprocess.Popen(
    [binary_path, '--mode', 'stdio'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,  # Merge stderr with stdout
    text=True,
    bufsize=0
)

def call_k8s_tool(tool_name, arguments=None):
    """Call a k8s-mcp-server tool and return the result"""
    if arguments is None:
        arguments = {}

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    server_process.stdin.write(json.dumps(request) + '\n')
    server_process.stdin.flush()

    response = server_process.stdout.readline()
    result = json.loads(response)

    # Extract the text content from the response
    if 'result' in result and 'content' in result['result']:
        return result['result']['content'][0]['text']
    elif 'error' in result:
        return f"Error: {result['error']['message']}"
    return str(result)

def get_available_tools():
    """Get list of available k8s-mcp-server tools"""
    import time
    # Wait a moment for server to start
    time.sleep(0.5)

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }

    server_process.stdin.write(json.dumps(request) + '\n')
    server_process.stdin.flush()

    # Read lines until we get a JSON response
    response = ""
    max_attempts = 10
    for _ in range(max_attempts):
        line = server_process.stdout.readline()
        if line.strip().startswith('{'):
            response = line
            break

    if not response:
        raise Exception("Failed to get response from k8s-mcp-server")

    result = json.loads(response)
    return result.get('result', {}).get('tools', [])

# Get available tools
tools = get_available_tools()
tool_list = [{"name": t['name'], "description": t['description']} for t in tools]

print("\n" + "=" * 50)
print("K8s MCP Server Interactive Chat")
print("=" * 50)
print(f"\nLoaded {len(tools)} Kubernetes tools")
print("Examples: 'list pods in gsoc namespace', 'get api resources', 'describe pod <name> in <namespace>'")
print("Type 'exit' to quit\n")

# Chat loop
conversation_history = [
    {
        "role": "system",
        "content": f"""You are a Kubernetes assistant. When the user asks about Kubernetes resources, you should:
1. Determine which tool to use from: {json.dumps(tool_list, indent=2)}
2. Respond with EXACTLY this format:
   TOOL: <tool_name>
   ARGS: {{"arg1": "value1", "arg2": "value2"}}

For example:
- "list pods in gsoc namespace" -> TOOL: listResources\\nARGS: {{"Kind": "Pod", "namespace": "gsoc"}}
- "get api resources" -> TOOL: getAPIResources\\nARGS: {{}}
- "describe pod xyz in gsoc" -> TOOL: describeResource\\nARGS: {{"Kind": "Pod", "name": "xyz", "namespace": "gsoc"}}

If the user is just asking questions without wanting to execute a tool, answer normally."""
    }
]

while True:
    try:
        user_input = input("You: ")
    except EOFError:
        print("\nGoodbye!")
        break

    if user_input.lower() in ['exit', 'quit']:
        print("Goodbye!")
        break

    conversation_history.append({
        "role": "user",
        "content": user_input
    })

    # Get AI response
    completion = client.chat.completions.create(
        model="deepseek-r1",
        messages=conversation_history
    )

    assistant_message = completion.choices[0].message.content

    # Check if the assistant wants to use a tool
    if "TOOL:" in assistant_message and "ARGS:" in assistant_message:
        lines = assistant_message.split('\n')
        tool_name = None
        args_json = None

        for i, line in enumerate(lines):
            if line.startswith("TOOL:"):
                tool_name = line.replace("TOOL:", "").strip()
            if line.startswith("ARGS:"):
                args_json = line.replace("ARGS:", "").strip()

        if tool_name and args_json:
            try:
                args = json.loads(args_json)
                print(f"\n🔧 Calling {tool_name}...")
                result = call_k8s_tool(tool_name, args)

                # Format the result nicely
                try:
                    result_data = json.loads(result)
                    if isinstance(result_data, list):
                        print(f"Found {len(result_data)} item(s):")
                        for item in result_data[:10]:  # Show first 10
                            if isinstance(item, dict):
                                name = item.get('name', item.get('kind', 'Unknown'))
                                print(f"  - {name}")
                            else:
                                print(f"  - {item}")
                        if len(result_data) > 10:
                            print(f"  ... and {len(result_data) - 10} more")
                    else:
                        print(json.dumps(result_data, indent=2))
                except:
                    print(result)

                conversation_history.append({
                    "role": "assistant",
                    "content": f"Executed {tool_name}, result: {result[:200]}..."
                })
            except Exception as e:
                print(f"❌ Error: {e}")
                conversation_history.append({
                    "role": "assistant",
                    "content": f"Error executing tool: {e}"
                })
    else:
        conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })
        print(f"\nAssistant: {assistant_message}\n")

# Cleanup
server_process.terminate()
server_process.wait()