import { beforeEach, describe, expect, it, vi } from "vitest";

const { sendCommandMock } = vi.hoisted(() => ({ sendCommandMock: vi.fn() }));

vi.mock("../src/utils/ConnectionManager.js", () => ({
  withApplicationConnection: async <T>(
    operation: (client: { sendCommand: typeof sendCommandMock }) => Promise<T>,
  ) => await operation({ sendCommand: sendCommandMock }),
}));

import { GEOMETRY_DOMAIN_DEFINITION } from "../src/tools/domains/geometryDomain.js";

describe("create_polyline arcs and layer", () => {
  beforeEach(() => {
    sendCommandMock.mockReset();
    sendCommandMock.mockResolvedValue({ handle: "1", vertexCount: 3, closed: false, layer: "CURB" });
  });

  it("forwards per-vertex bulge and layer to the plugin", async () => {
    const action = GEOMETRY_DOMAIN_DEFINITION.actions.create_polyline;
    const args = action.inputSchema.parse({
      action: "create_polyline",
      layer: "CURB",
      points: [{ x: 0, y: 0, bulge: 0.4142 }, { x: 10, y: 10 }, { x: 20, y: 10 }],
    });
    await action.execute(args as never, {} as never);
    expect(sendCommandMock).toHaveBeenCalledWith("createPolyline", expect.objectContaining({
      layer: "CURB",
      points: [{ x: 0, y: 0, bulge: 0.4142 }, { x: 10, y: 10 }, { x: 20, y: 10 }],
    }));
  });
});
