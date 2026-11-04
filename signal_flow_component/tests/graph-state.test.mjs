import test from "node:test";
import assert from "node:assert/strict";
import { mergeNodePositions, selectSignal } from "../src/graph-state.mjs";

test("endpoint refresh preserves a dragged node and gives new nodes a default position", () => {
  const previous = [{ id: "signal:5", position: { x: 410, y: 120 } }];
  const incoming = [
    { id: "signal:5", position: { x: 350, y: 70 }, data: { receiverCount: 2 } },
    { id: "rx:ADAS", position: { x: 940, y: 100 } },
  ];
  const merged = mergeNodePositions(previous, incoming);
  assert.deepEqual(merged[0].position, previous[0].position);
  assert.equal(merged[0].data.receiverCount, 2);
  assert.deepEqual(merged[1].position, incoming[1].position);
  assert.deepEqual(incoming[0].position, { x: 350, y: 70 });
});

test("switching selected signals clears the previous highlight including numeric/string IDs", () => {
  const nodes = [
    { id: "tx", type: "endpoint", data: { kind: "tx" } },
    { id: "signal:1", type: "signal", data: { signalId: 1, selected: true } },
    { id: "signal:5", type: "signal", data: { signalId: 5, selected: false } },
  ];
  const result = selectSignal(nodes, "5");
  assert.equal(result.filter((node) => node.data.selected).length, 1);
  assert.equal(result[2].data.selected, true);
  assert.equal(result[0], nodes[0]);
  assert.equal(nodes[1].data.selected, true);
});
