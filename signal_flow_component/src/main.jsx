import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Background,
  BaseEdge,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  getBezierPath,
  getSmoothStepPath,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./style.css";
import { mergeNodePositions, selectSignal } from "./graph-state.mjs";

const send = (type, extra = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...extra }, "*");
const setHeight = (height) => send("streamlit:setFrameHeight", { height });
const setValue = (value) => send("streamlit:setComponentValue", { value, dataType: "json" });
const nonce = () => Date.now().toString(36) + Math.random().toString(36).slice(2);
const keyFor = (args) => `ee-req-react-flow:${args?.viewStateKey || "default"}`;

function readViewport(args) {
  try { return JSON.parse(sessionStorage.getItem(keyFor(args)) || "null"); } catch { return null; }
}

function writeViewport(args, viewport) {
  try { sessionStorage.setItem(keyFor(args), JSON.stringify(viewport)); } catch { /* session storage is optional */ }
}

const EndpointNode = memo(({ data, selected }) => (
  <div className={`flow-node endpoint-node ${selected ? "selected" : ""}`}>
    {data.kind === "rx" && <Handle id="target" type="target" position={Position.Left} className="endpoint target-endpoint" />}
    <div className="node-code">{data.label}</div>
    <div className="node-meta">{data.meta}</div>
    {data.kind === "tx" && <Handle id="source" type="source" position={Position.Right} />}
  </div>
));

const SignalNode = memo(({ id, data }) => (
  <div
    className={`signal-node node-signal ${data.selected ? "selected" : ""}`}
    data-signal-id={data.signalId}
    onClick={(event) => { event.stopPropagation(); data.onSelect(data.signalId); }}
  >
    <Handle id="input" type="target" position={Position.Left} />
    <div className="signal-copy">
      <div className="node-code">{data.label}</div>
      <div className="node-meta">{data.meta}</div>
    </div>
    <span className="rx-count">RX {data.receiverCount}</span>
    <Handle
      id="add"
      type="source"
      position={Position.Right}
      className="branch-handle"
      data-signal-id={data.signalId}
      title="拖到 ECU：新增接收分支"
      isConnectable
    />
  </div>
));

const MessageNode = memo(({ data }) => (
  <div className="flow-node message-node">
    <Handle id="input" type="target" position={Position.Left} />
    <div className="node-code">{data.label}</div>
    <div className="node-meta">{data.meta}</div>
    <Handle id="source" type="source" position={Position.Right} />
  </div>
));

function FlowEdge(props) {
  const [path] = props.data?.lineStyle === "orthogonal"
    ? getSmoothStepPath(props)
    : getBezierPath(props);
  return (
    <BaseEdge
      {...props}
      path={path}
      className={`flow-edge ${props.data?.override ? "override" : ""}`}
      markerEnd={props.markerEnd}
      interactionWidth={18}
    />
  );
}

const nodeTypes = { endpoint: EndpointNode, signal: SignalNode, message: MessageNode };
const edgeTypes = { flow: FlowEdge };

function buildModel(args, onSelect) {
  const signals = args.signals || [];
  const tx = args.message?.tx || "未分配发送节点";
  const nodes = [{
    id: "tx", type: "endpoint", position: { x: 40, y: 250 },
    data: { kind: "tx", label: tx, meta: "TRANSMITTER" }, draggable: true,
  }];
  const edges = [];
  const actualReceivers = signals.flatMap((signal) => (signal.receivers || []).map((item) => item.ecu));
  const receiverNames = [...new Set([...actualReceivers, ...(args.ecuCandidates || [])])].filter(Boolean);
  if (!receiverNames.length) receiverNames.push("未分配接收节点");

  receiverNames.forEach((ecu, index) => {
    const count = signals.reduce((sum, signal) => sum + (signal.receivers || []).filter((item) => item.ecu === ecu).length, 0);
    nodes.push({
      id: `rx:${ecu}`, type: "endpoint", position: { x: 940, y: 100 + index * 90 },
      data: { kind: "rx", label: ecu, meta: `RX · ${count} ENDPOINTS` }, draggable: true,
    });
  });

  if (args.mode === "aggregate") {
    nodes.push({
      id: "message", type: "message", position: { x: 360, y: 245 },
      data: { label: args.message?.name || "未命名报文", meta: `${args.message?.id || "—"} · ${signals.length} signals · ${args.message?.bus || "—"}` },
    });
    edges.push({ id: "tx-message", source: "tx", target: "message", type: "flow", data: { lineStyle: args.lineStyle } });
    receiverNames.filter((ecu) => actualReceivers.includes(ecu)).forEach((ecu) => edges.push({
      id: `message-rx:${ecu}`, source: "message", target: `rx:${ecu}`, type: "flow", data: { lineStyle: args.lineStyle },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#ff6b35" },
    }));
    return { nodes, edges };
  }

  const step = args.compact ? 64 : 78;
  signals.forEach((signal, index) => {
    const signalNodeId = `signal:${signal.id}`;
    nodes.push({
      id: signalNodeId,
      type: "signal",
      position: { x: 350, y: 70 + index * step },
      data: {
        signalId: Number(signal.id),
        label: signal.name,
        meta: `${signal.signal_id} · ${signal.start_bit ?? "?"}|${signal.bit_length ?? "?"} · ${signal.unit || "—"}`,
        receiverCount: (signal.receivers || []).length,
        selected: Number(args.selectedSignalId) === Number(signal.id),
        onSelect,
      },
    });
    edges.push({ id: `tx-${signalNodeId}`, source: "tx", target: signalNodeId, targetHandle: "input", type: "flow", data: { lineStyle: args.lineStyle } });
    (signal.receivers || []).forEach((endpoint) => {
      const override = Boolean(endpoint.is_override);
      edges.push({
        id: `endpoint:${endpoint.endpoint_id}`,
        source: signalNodeId,
        sourceHandle: "add",
        target: `rx:${endpoint.ecu}`,
        targetHandle: "target",
        type: "flow",
        reconnectable: true,
        data: {
          signalId: Number(signal.id), endpointId: Number(endpoint.endpoint_id), oldEcu: endpoint.ecu,
          override, lineStyle: args.lineStyle,
        },
        className: "endpoint",
        "data-endpoint-id": endpoint.endpoint_id,
        markerEnd: { type: MarkerType.ArrowClosed, color: override ? "#27d3c2" : "#ff6b35" },
      });
    });
  });
  return { nodes, edges };
}

async function elkLayout(nodes, edges) {
  const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
  const elk = new ELK();
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.spacing.nodeNode": "28",
      "elk.layered.spacing.nodeNodeBetweenLayers": "90",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: node.type === "signal" ? 390 : (node.type === "message" ? 320 : 210),
      height: node.type === "signal" ? 56 : 70,
    })),
    edges: edges.map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  };
  const result = await elk.layout(graph);
  const positions = Object.fromEntries((result.children || []).map((node) => [node.id, { x: node.x, y: node.y }]));
  return nodes.map((node) => ({ ...node, position: positions[node.id] || node.position }));
}

function FlowCanvas({ args }) {
  const wrapperRef = useRef(null);
  const modelKeyRef = useRef("");
  const viewKeyRef = useRef(args.viewStateKey);
  const pendingSelectionRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const reactFlow = useReactFlow();
  const emit = useCallback((payload) => {
    const viewport = reactFlow.getViewport();
    writeViewport(args, viewport);
    setValue({ ...payload, viewport, nonce: nonce() });
  }, [args, reactFlow]);
  const onSelect = useCallback((signalId) => {
    pendingSelectionRef.current = Number(signalId);
    setNodes((current) => selectSignal(current, signalId));
    emit({ action: "select_signal", signal_id: signalId });
  }, [emit]);
  const initial = useMemo(() => buildModel(args, onSelect), [args, onSelect]);
  const [nodes, setNodes] = useState(initial.nodes);
  const [edges, setEdges] = useState(initial.edges);

  const modelKey = JSON.stringify({
    mode: args.mode,
    message: args.message,
    candidates: args.ecuCandidates,
    compact: args.compact,
    lineStyle: args.lineStyle,
    signals: (args.signals || []).map((signal) => ({
      id: signal.id,
      name: signal.name,
      start: signal.start_bit,
      length: signal.bit_length,
      receivers: signal.receivers,
    })),
  });
  useEffect(() => {
    const sameView = viewKeyRef.current === args.viewStateKey;
    if (!sameView) pendingSelectionRef.current = null;
    const selectedId = pendingSelectionRef.current ?? args.selectedSignalId;
    if (Number(args.selectedSignalId) === pendingSelectionRef.current) {
      pendingSelectionRef.current = null;
    }
    if (modelKeyRef.current !== modelKey) {
      modelKeyRef.current = modelKey;
      viewKeyRef.current = args.viewStateKey;
      setNodes((current) => selectSignal(
        sameView ? mergeNodePositions(current, initial.nodes) : initial.nodes, selectedId,
      ));
      setEdges(initial.edges);
      return;
    }
    setNodes((current) => selectSignal(current, selectedId));
  }, [args.selectedSignalId, args.viewStateKey, initial, modelKey]);

  const onInit = useCallback((instance) => {
    const saved = args.viewportState?.x != null ? args.viewportState : readViewport(args);
    if (saved?.x != null) instance.setViewport(saved, { duration: 0 });
    else instance.fitView({ padding: 0.12, duration: 0 });
  }, [args]);
  const onMoveEnd = useCallback((_event, viewport) => writeViewport(args, viewport), [args]);

  const onConnect = useCallback((connection) => {
    if (args.mode !== "detail" || !connection.source?.startsWith("signal:") || !connection.target?.startsWith("rx:")) return;
    const signalId = Number(connection.source.slice(7));
    const newEcu = connection.target.slice(3);
    const signal = (args.signals || []).find((item) => Number(item.id) === signalId);
    if (!newEcu || newEcu.startsWith("未分配") || (signal?.receivers || []).some((item) => item.ecu === newEcu)) return;
    emit({ action: "add_receiver", signal_id: signalId, new_ecu: newEcu });
  }, [args, emit]);

  const onReconnect = useCallback((oldEdge, connection) => {
    if (!connection.target?.startsWith("rx:") || !oldEdge.data?.endpointId) return;
    const newEcu = connection.target.slice(3);
    if (!newEcu || newEcu === oldEdge.data.oldEcu || newEcu.startsWith("未分配")) return;
    emit({
      action: "move_receiver",
      signal_id: oldEdge.data.signalId,
      endpoint_id: oldEdge.data.endpointId,
      old_ecu: oldEdge.data.oldEcu,
      new_ecu: newEcu,
    });
  }, [emit]);

  const autoLayout = useCallback(async () => {
    const arranged = await elkLayout(nodes, edges);
    setNodes(arranged);
    requestAnimationFrame(() => reactFlow.fitView({ padding: 0.12, duration: 300 }));
  }, [nodes, edges, reactFlow]);

  const toggleFullscreen = useCallback(async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  }, []);

  const exportPng = useCallback(async () => {
    if (!wrapperRef.current) return;
    const { toPng } = await import("html-to-image");
    const url = await toPng(wrapperRef.current, { backgroundColor: "#111c23", pixelRatio: 2 });
    const link = document.createElement("a");
    link.download = `${args.message?.name || "signal-flow"}.png`;
    link.href = url;
    link.click();
  }, [args]);

  useEffect(() => {
    const updateFullscreen = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => document.removeEventListener("fullscreenchange", updateFullscreen);
  }, []);

  return (
    <div className="shell">
      <div className="toolbar">
        <div><div className="eyebrow">{args.mode === "aggregate" ? "MESSAGE AGGREGATE" : "SIGNAL ENDPOINT EDIT"}</div><div className="title">{args.message?.name || "未命名报文"}</div></div>
        <div className="hint">{args.mode === "detail" ? "从信号右侧拖到 ECU 新增分支；拖动连线末端切换接收节点" : "按报文聚合展示真实有效端点"}</div>
        <div className="toolbar-spacer" />
        <div className="legend"><span><i />DBC</span><span><i className="manual" />项目变更</span></div>
        <button type="button" onClick={autoLayout}>自动排版</button>
        <button type="button" onClick={toggleFullscreen}>{isFullscreen ? "退出全屏" : "全屏"}</button>
        <button type="button" onClick={exportPng}>PNG</button>
        <div className="badge">{(args.signals || []).length} SIGNALS</div>
      </div>
      <div className="viewport" ref={wrapperRef}>
        <div className="endpoint-metadata" aria-hidden="true">
          {(args.signals || []).flatMap((signal) => (signal.receivers || []).map((endpoint) => (
            <span
              key={endpoint.endpoint_id}
              className="endpoint"
              data-endpoint-id={endpoint.endpoint_id}
              data-old-ecu={endpoint.ecu}
              data-signal-id={signal.id}
            />
          )))}
        </div>
        <div className="lane-label source">SOURCE ECU</div><div className="lane-label signals">{args.mode === "aggregate" ? "CAN MESSAGE" : "SIGNALS"}</div><div className="lane-label receiver">RECEIVER ECU</div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={(changes) => setNodes((current) => applyNodeChanges(changes, current))}
          onEdgesChange={() => {}}
          onConnect={onConnect}
          onReconnect={onReconnect}
          onInit={onInit}
          onMoveEnd={onMoveEnd}
          nodesDraggable
          edgesReconnectable
          minZoom={0.25}
          maxZoom={2.2}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#29404d" gap={24} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}

function App() {
  const [args, setArgs] = useState(null);
  useEffect(() => {
    const listener = (event) => {
      if (event.data?.type === "streamlit:render") setArgs(event.data.args || {});
    };
    window.addEventListener("message", listener);
    send("streamlit:componentReady", { apiVersion: 1 });
    return () => window.removeEventListener("message", listener);
  }, []);
  useEffect(() => {
    const height = Math.max(590, Math.min(880, Math.round((window.screen?.availHeight || 900) * 0.76)));
    setHeight(height);
  }, [args]);
  if (!args) return null;
  if (!(args.signals || []).length) return <div className="empty">当前筛选条件下没有信号数据</div>;
  return <ReactFlowProvider><FlowCanvas args={args} /></ReactFlowProvider>;
}

createRoot(document.getElementById("root")).render(<App />);
