import { useState, useCallback } from "react";
import { streamChat } from "../api/client";
import type { ChatMessage, ToolCallEntry } from "../types";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = useCallback(async (content: string) => {
    const userMsg: ChatMessage = { role: "user", content };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);

    const apiMessages = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const toolCalls: ToolCallEntry[] = [];
    let assistantText = "";

    try {
      for await (const event of streamChat(apiMessages)) {
        switch (event.event) {
          case "tool_call":
            toolCalls.push({
              name: event.data.name as string,
              arguments: event.data.arguments as Record<string, unknown>,
              result: "",
            });
            // Update message in real-time to show tool call
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last?.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  tool_calls: [...toolCalls],
                };
              } else {
                updated.push({
                  role: "assistant",
                  content: "",
                  tool_calls: [...toolCalls],
                });
              }
              return updated;
            });
            break;

          case "tool_result":
            if (toolCalls.length > 0) {
              toolCalls[toolCalls.length - 1].result = event.data.result as string;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    tool_calls: [...toolCalls],
                  };
                }
                return updated;
              });
            }
            break;

          case "content":
            assistantText = event.data.text as string;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last?.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: assistantText,
                };
              } else {
                updated.push({
                  role: "assistant",
                  content: assistantText,
                  tool_calls: toolCalls.length > 0 ? [...toolCalls] : undefined,
                });
              }
              return updated;
            });
            break;

          case "error":
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: `Error: ${event.data.message}`,
              },
            ]);
            break;
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : String(err)}`,
        },
      ]);
    } finally {
      setIsStreaming(false);
    }
  }, [messages]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return { messages, isStreaming, sendMessage, clearMessages };
}
