/** Preserve manual positions when server updates endpoints in the same view. */
export function mergeNodePositions(previous, incoming) {
  const positions = new Map(previous.map((node) => [node.id, node.position]));
  return incoming.map((node) => ({ ...node, position: positions.get(node.id) ?? node.position }));
}

/** The inspector and canvas share one selected signal ID. */
export function selectSignal(nodes, signalId) {
  return nodes.map((node) => node.type === "signal"
    ? { ...node, data: { ...node.data, selected: Number(node.data.signalId) === Number(signalId) } }
    : node);
}
