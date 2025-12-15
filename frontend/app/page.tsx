"use client";

import { useState } from "react";

export default function Home() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; content: string }[]
  >([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || isLoading) return;

    const userMessage = message.trim();
    setMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/chat/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: userMessage }),
        }
      );

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.content },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error connecting to the API. Make sure the backend is running.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="border-b border-white/10 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-1 bg-f1-red rounded-full" />
          <h1 className="text-xl font-bold">F1 Race Intelligence Agent</h1>
          <span className="text-xs text-white/40 bg-background-tertiary px-2 py-1 rounded">
            v0.1.0
          </span>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex flex-col max-w-4xl mx-auto w-full p-6">
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto space-y-4 mb-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="text-6xl mb-4">🏎️</div>
              <h2 className="text-2xl font-bold mb-2">
                Your Race Engineer Co-Pilot
              </h2>
              <p className="text-white/60 max-w-md mb-8">
                Ask me anything about F1 races, strategies, telemetry, and more.
                I can analyze data from 2018-2024.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-lg">
                {[
                  "Compare Verstappen and Norris at Singapore 2024",
                  "Show me Hamilton's fastest lap at Monaco",
                  "Why did Ferrari's strategy fail at Silverstone?",
                  "What if Max had pitted earlier at Abu Dhabi?",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setMessage(suggestion)}
                    className="f1-button-secondary text-sm text-left"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-background-tertiary"
                      : "bg-background-secondary border border-white/5"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))
          )}

          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-background-secondary border border-white/5 rounded-lg px-4 py-3">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-f1-red rounded-full animate-pulse" />
                  <span className="w-2 h-2 bg-f1-red rounded-full animate-pulse delay-100" />
                  <span className="w-2 h-2 bg-f1-red rounded-full animate-pulse delay-200" />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input area */}
        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Ask about F1 races, strategies, telemetry..."
            className="f1-input flex-1"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={!message.trim() || isLoading}
            className="f1-button"
          >
            Send
          </button>
        </form>

        {/* Footer note */}
        <p className="text-xs text-white/30 text-center mt-4">
          Data powered by FastF1 • Agent not yet implemented • Phase 1 skeleton
        </p>
      </div>
    </main>
  );
}
