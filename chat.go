package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

const (
	apiKey      = "8cAW1wtB6KyXcZ8GenYEu4Bfrz7DQvGA"
	baseURL     = "https://ellm.nrp-nautilus.io/v1"
	mcpServerURL = "http://localhost:8080"
)

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatRequest struct {
	Model       string    `json:"model"`
	Messages    []Message `json:"messages"`
	Temperature float64   `json:"temperature"`
}

type ChatResponse struct {
	Choices []struct {
		Message Message `json:"message"`
	} `json:"choices"`
}

type MCPRequest struct {
	JSONRPC string                 `json:"jsonrpc"`
	ID      int                    `json:"id"`
	Method  string                 `json:"method"`
	Params  map[string]interface{} `json:"params"`
}

type MCPResponse struct {
	Result struct {
		Tools   []map[string]interface{} `json:"tools,omitempty"`
		Content []struct {
			Text string `json:"text"`
		} `json:"content,omitempty"`
	} `json:"result,omitempty"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

var serverProcess *exec.Cmd

func main() {
	// Check if server is already running, otherwise start it
	fmt.Println("🔍 Checking if k8s-mcp-server is already running...")

	client := &http.Client{Timeout: 1 * time.Second}
	_, err := client.Get(mcpServerURL)

	if err != nil {
		fmt.Println("🚀 Starting k8s-mcp-server in streamable-http mode...")

		binaryName := "k8s-mcp-server"
		if runtime.GOOS == "windows" {
			binaryName = "k8s-mcp-server.exe"
		}

		serverProcess = exec.Command(binaryName, "--mode", "streamable-http", "--port", "8080")
		serverProcess.Env = append(os.Environ(), fmt.Sprintf("HOME=%s", os.Getenv("USERPROFILE")))

		if err := serverProcess.Start(); err != nil {
			fmt.Printf("❌ Failed to start server: %v\n", err)
			os.Exit(1)
		}

		fmt.Println("⏳ Waiting for server to start...")
		time.Sleep(3 * time.Second)
	} else {
		fmt.Println("✅ Server is already running on port 8080")
	}

	// Get available tools
	tools := getAvailableTools()
	if len(tools) == 0 {
		fmt.Println("❌ Failed to connect to k8s-mcp-server.")
		cleanup()
		os.Exit(1)
	}

	// Build tool descriptions for system prompt
	toolDescriptions := make([]map[string]interface{}, len(tools))
	for i, tool := range tools {
		toolDescriptions[i] = map[string]interface{}{
			"name":        tool["name"],
			"description": tool["description"],
			"inputSchema": tool["inputSchema"],
		}
	}

	toolsJSON, _ := json.MarshalIndent(toolDescriptions, "", "  ")

	fmt.Println("\n" + strings.Repeat("=", 60))
	fmt.Println("💬 K8s Chat with DeepSeek-R1 + MCP Server")
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("✅ Loaded %d Kubernetes tools\n", len(tools))
	fmt.Println("\n💡 Examples:")
	fmt.Println("  • List all pods in the gsoc namespace")
	fmt.Println("  • Show me the API resources")
	fmt.Println("  • Describe the xyz pod in gsoc namespace")
	fmt.Println("  • What deployments are running?")
	fmt.Println("\nType 'exit' or 'quit' to end the conversation\n")

	// Initialize conversation with system prompt
	systemPrompt := fmt.Sprintf(`You are an expert Kubernetes assistant with access to a real K8s cluster via MCP tools.

Available tools:
%s

When users ask about Kubernetes resources:
1. Determine which tool(s) to use based on their question
2. Respond in this EXACT format:
   TOOL: <tool_name>
   ARGS: {"param": "value"}

3. After tool execution, interpret the results naturally for the user

Common patterns:
- "list/show pods" → listResources with Kind="Pod"
- "get api resources" → getAPIResources
- "describe <resource>" → describeResource with Kind, name, namespace
- "what namespaces" → listResources with Kind="Namespace"

If no tool is needed (general questions), respond conversationally.`, string(toolsJSON))

	conversationHistory := []Message{
		{Role: "system", Content: systemPrompt},
	}

	// Chat loop
	reader := bufio.NewReader(os.Stdin)

	for {
		fmt.Print("You: ")
		userInput, err := reader.ReadString('\n')
		if err != nil {
			fmt.Println("\n👋 Goodbye!")
			break
		}

		userInput = strings.TrimSpace(userInput)

		if userInput == "" {
			continue
		}

		if userInput == "exit" || userInput == "quit" || userInput == "bye" {
			fmt.Println("👋 Goodbye!")
			break
		}

		conversationHistory = append(conversationHistory, Message{
			Role:    "user",
			Content: userInput,
		})

		// Get AI response
		assistantMessage, err := getChatCompletion(conversationHistory)
		if err != nil {
			fmt.Printf("❌ Error: %v\n\n", err)
			continue
		}

		// Check if assistant wants to use a tool
		if strings.Contains(assistantMessage, "TOOL:") && strings.Contains(assistantMessage, "ARGS:") {
			lines := strings.Split(assistantMessage, "\n")
			var toolName, argsJSON string

			for _, line := range lines {
				line = strings.TrimSpace(line)
				if strings.HasPrefix(line, "TOOL:") {
					toolName = strings.TrimSpace(strings.TrimPrefix(line, "TOOL:"))
				} else if strings.HasPrefix(line, "ARGS:") {
					argsJSON = strings.TrimSpace(strings.TrimPrefix(line, "ARGS:"))
				}
			}

			if toolName != "" && argsJSON != "" {
				var args map[string]interface{}
				if err := json.Unmarshal([]byte(argsJSON), &args); err != nil {
					fmt.Printf("❌ Invalid JSON in args: %v\n", err)
					continue
				}

				argsBytes, _ := json.Marshal(args)
				fmt.Printf("\n🔧 Executing: %s(%s)\n", toolName, string(argsBytes))

				result := callK8sTool(toolName, args)

				// Display results nicely
				fmt.Println("\n📋 Results:")
				displayResults(result)

				// Add tool result to conversation for context
				truncatedResult := result
				if len(result) > 500 {
					truncatedResult = result[:500]
				}

				conversationHistory = append(conversationHistory, Message{
					Role:    "assistant",
					Content: fmt.Sprintf("Tool %s executed successfully. Result: %s", toolName, truncatedResult),
				})

				// Ask AI to interpret the results
				conversationHistory = append(conversationHistory, Message{
					Role:    "user",
					Content: "Please summarize what we found in a natural way.",
				})

				interpretation, err := getChatCompletion(conversationHistory)
				if err != nil {
					fmt.Printf("❌ Error getting interpretation: %v\n", err)
					continue
				}

				fmt.Printf("\n🤖 Assistant: %s\n\n", interpretation)

				conversationHistory = append(conversationHistory, Message{
					Role:    "assistant",
					Content: interpretation,
				})
			}
		} else {
			// Regular conversation response
			fmt.Printf("\n🤖 Assistant: %s\n\n", assistantMessage)
			conversationHistory = append(conversationHistory, Message{
				Role:    "assistant",
				Content: assistantMessage,
			})
		}
	}

	cleanup()
}

func getChatCompletion(messages []Message) (string, error) {
	reqBody := ChatRequest{
		Model:       "deepseek-r1",
		Messages:    messages,
		Temperature: 0.7,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequest("POST", baseURL+"/chat/completions", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	var chatResp ChatResponse
	if err := json.Unmarshal(body, &chatResp); err != nil {
		return "", fmt.Errorf("failed to parse response: %w (body: %s)", err, string(body))
	}

	if len(chatResp.Choices) == 0 {
		return "", fmt.Errorf("no response from AI")
	}

	return chatResp.Choices[0].Message.Content, nil
}

func callK8sTool(toolName string, arguments map[string]interface{}) string {
	reqData := MCPRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  "tools/call",
		Params: map[string]interface{}{
			"name":      toolName,
			"arguments": arguments,
		},
	}

	jsonData, err := json.Marshal(reqData)
	if err != nil {
		return fmt.Sprintf("Error marshaling request: %v", err)
	}

	resp, err := http.Post(mcpServerURL+"/mcp", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Sprintf("Error calling tool: %v", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Sprintf("Error reading response: %v", err)
	}

	var mcpResp MCPResponse
	if err := json.Unmarshal(body, &mcpResp); err != nil {
		return fmt.Sprintf("Error parsing response: %v", err)
	}

	if mcpResp.Error != nil {
		return fmt.Sprintf("Error: %s", mcpResp.Error.Message)
	}

	if len(mcpResp.Result.Content) > 0 {
		return mcpResp.Result.Content[0].Text
	}

	return string(body)
}

func getAvailableTools() []map[string]interface{} {
	reqData := MCPRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  "tools/list",
		Params:  map[string]interface{}{},
	}

	jsonData, err := json.Marshal(reqData)
	if err != nil {
		fmt.Printf("❌ Error marshaling request: %v\n", err)
		return nil
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Post(mcpServerURL+"/mcp", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		fmt.Printf("❌ Error getting tools: %v\n", err)
		return nil
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		fmt.Printf("❌ Error reading response: %v\n", err)
		return nil
	}

	var mcpResp MCPResponse
	if err := json.Unmarshal(body, &mcpResp); err != nil {
		fmt.Printf("❌ Error parsing response: %v\n", err)
		return nil
	}

	return mcpResp.Result.Tools
}

func displayResults(result string) {
	var data interface{}
	if err := json.Unmarshal([]byte(result), &data); err != nil {
		// Not JSON, just print it
		if len(result) > 1000 {
			fmt.Println(result[:1000])
		} else {
			fmt.Println(result)
		}
		return
	}

	switch v := data.(type) {
	case []interface{}:
		fmt.Printf("Found %d item(s):\n", len(v))
		for i, item := range v {
			if i >= 15 {
				fmt.Printf("  ... and %d more\n", len(v)-15)
				break
			}

			if m, ok := item.(map[string]interface{}); ok {
				name := "Unknown"
				if n, ok := m["name"].(string); ok {
					name = n
				} else if k, ok := m["kind"].(string); ok {
					name = k
				}

				namespace := ""
				if ns, ok := m["namespace"].(string); ok {
					namespace = ns
				}

				if namespace != "" {
					fmt.Printf("  • %s (namespace: %s)\n", name, namespace)
				} else {
					fmt.Printf("  • %s\n", name)
				}
			} else {
				fmt.Printf("  • %v\n", item)
			}
		}
	default:
		prettyJSON, _ := json.MarshalIndent(data, "", "  ")
		fmt.Println(string(prettyJSON))
	}
}

func cleanup() {
	if serverProcess != nil {
		fmt.Println("🧹 Cleaning up...")
		serverProcess.Process.Kill()
	}
}
