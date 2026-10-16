import { beforeEach, describe, expect, it, vi } from "vitest";

const { sendCommandMock } = vi.hoisted(() => ({
  sendCommandMock: vi.fn(),
}));

vi.mock("../src/utils/ConnectionManager.js", () => ({
  withApplicationConnection: async <T>(
    operation: (client: { sendCommand: typeof sendCommandMock }) => Promise<T>,
  ) => await operation({
    sendCommand: sendCommandMock,
  }),
}));

import { POINT_DOMAIN_DEFINITION } from "../src/tools/domains/pointDomain.js";

describe("point list filters", () => {
  beforeEach(() => {
    sendCommandMock.mockReset();
    sendCommandMock.mockResolvedValue({ totalCount: 0, returnedCount: 0, points: [], units: "feet" });
  });

  it("accepts and forwards number, description, layer and window filters", async () => {
    const action = POINT_DOMAIN_DEFINITION.actions.list;
    const args = action.inputSchema.parse({
      action: "list",
      includeNumbers: "62126-62140",
      excludeNumbers: "62130",
      includeDescriptions: "TC*,*LO",
      layers: ["PTS-CRB"],
      window: { minX: 1, minY: 2, maxX: 3, maxY: 4 },
      limit: 50,
    });

    await action.execute(args as never, {} as never);

    expect(sendCommandMock).toHaveBeenCalledWith("listCogoPoints", expect.objectContaining({
      includeNumbers: "62126-62140",
      excludeNumbers: "62130",
      includeDescriptions: "TC*,*LO",
      layers: ["PTS-CRB"],
      window: { minX: 1, minY: 2, maxX: 3, maxY: 4 },
      limit: 50,
    }));
  });

  it("rejects a window missing a corner", () => {
    const action = POINT_DOMAIN_DEFINITION.actions.list;
    expect(() => action.inputSchema.parse({ action: "list", window: { minX: 1, minY: 2, maxX: 3 } })).toThrow();
  });
});
