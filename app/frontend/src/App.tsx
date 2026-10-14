import { useState, useCallback } from "react";
import Sidebar from "./components/Sidebar";
import Chat from "./components/Chat";
import DataView from "./components/DataView";
import PipelineView from "./components/PipelineView";
import NiFiFlows from "./components/NiFiFlows";
import SparkJobs from "./components/SparkJobs";
import MetadataFiles from "./components/MetadataFiles";
import Classifications from "./components/Classifications";
import { useChat } from "./hooks/useChat";
import { usePipeline } from "./hooks/usePipeline";
import { useSettings } from "./hooks/useSettings";
import type { DataStatus } from "./types";
import "./App.css";

function App() {
  const [activeTab, setActiveTab] = useState<"chat" | "data" | "pipeline" | "nifi" | "spark" | "metadata" | "classification">("chat");
  const [dataStatus, setDataStatus] = useState<DataStatus>({ loaded: false });
  const { messages, isStreaming, sendMessage, clearMessages } = useChat();
  const pipeline = usePipeline();
  const { logoUrl, setLogoUrl } = useSettings();

  const handleQuickAction = useCallback(
    (action: string) => {
      setActiveTab("chat");
      sendMessage(action);
    },
    [sendMessage]
  );

  const handleDataLoaded = useCallback(
    (status: DataStatus) => {
      setDataStatus(status);
      if (status.loaded) {
        setActiveTab("pipeline");
        pipeline.startPipeline();
      }
    },
    [pipeline]
  );

  const handleRerunPipeline = useCallback(() => {
    setActiveTab("pipeline");
    pipeline.startPipeline();
  }, [pipeline]);

  return (
    <div className="app">
      <Sidebar
        dataStatus={dataStatus}
        setDataStatus={setDataStatus}
        onDataLoaded={handleDataLoaded}
        onQuickAction={handleQuickAction}
        pipelineRunning={pipeline.isRunning}
        pipelineRuleCount={pipeline.rules.length}
        onRerunPipeline={handleRerunPipeline}
        logoUrl={logoUrl}
        onLogoChange={setLogoUrl}
      />
      <main className="main">
        <nav className="tab-nav">
          <button className={activeTab === "chat" ? "active" : ""} onClick={() => setActiveTab("chat")}>
            Chat
          </button>
          <button
            className={activeTab === "data" ? "active" : ""}
            onClick={() => setActiveTab("data")}
            disabled={!dataStatus.loaded}
          >
            Data
          </button>
          <button
            className={activeTab === "pipeline" ? "active" : ""}
            onClick={() => setActiveTab("pipeline")}
            disabled={!dataStatus.loaded}
          >
            Pipeline
          </button>
          <button
            className={activeTab === "metadata" ? "active" : ""}
            onClick={() => setActiveTab("metadata")}
            disabled={!dataStatus.loaded}
          >
            Metadata
          </button>
          <button
            className={activeTab === "classification" ? "active" : ""}
            onClick={() => setActiveTab("classification")}
            disabled={!dataStatus.loaded}
          >
            Classification
          </button>
          <button
            className={activeTab === "nifi" ? "active" : ""}
            onClick={() => setActiveTab("nifi")}
            disabled={!dataStatus.loaded}
          >
            NiFi Flows
          </button>
          <button
            className={activeTab === "spark" ? "active" : ""}
            onClick={() => setActiveTab("spark")}
            disabled={!dataStatus.loaded}
          >
            Spark Jobs
          </button>
          {activeTab === "chat" && messages.length > 0 && (
            <button className="clear-btn" onClick={clearMessages}>Clear Chat</button>
          )}
          <img
            src={logoUrl}
            alt="Logo"
            className="nav-logo"
          />
        </nav>
        <div className="tab-content">
          {activeTab === "chat" && (
            <Chat
              messages={messages}
              isStreaming={isStreaming}
              onSend={sendMessage}
            />
          )}
          {activeTab === "data" && dataStatus.loaded && (
            <DataView profiles={pipeline.profiles} />
          )}
          {activeTab === "pipeline" && dataStatus.loaded && (
            <PipelineView
              currentStage={pipeline.currentStage}
              isRunning={pipeline.isRunning}
              error={pipeline.error}
              profiles={pipeline.profiles}
              issues={pipeline.issues}
              rules={pipeline.rules}
              schemaText={pipeline.schemaText}
              completedStages={pipeline.completedStages}
              onToggleRule={pipeline.toggleRule}
              onToggleAllRules={pipeline.toggleAllRules}
              onUpdateRule={pipeline.updateRule}
              onSwitchToNiFi={() => setActiveTab("nifi")}
              onSwitchToSpark={() => setActiveTab("spark")}
              onSwitchToMetadata={() => setActiveTab("metadata")}
              onSwitchToClassification={() => setActiveTab("classification")}
              generatedNifiId={pipeline.generatedNifiId}
              generatedSparkId={pipeline.generatedSparkId}
              generatedMetadataId={pipeline.generatedMetadataId}
              generatedClassificationId={pipeline.generatedClassificationId}
            />
          )}
          {activeTab === "nifi" && dataStatus.loaded && <NiFiFlows focusId={pipeline.generatedNifiId} />}
          {activeTab === "spark" && dataStatus.loaded && <SparkJobs focusId={pipeline.generatedSparkId} />}
          {activeTab === "metadata" && dataStatus.loaded && <MetadataFiles focusId={pipeline.generatedMetadataId} />}
          {activeTab === "classification" && dataStatus.loaded && <Classifications />}
        </div>
      </main>
    </div>
  );
}

export default App;
