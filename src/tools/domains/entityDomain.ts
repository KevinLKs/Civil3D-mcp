import { z } from "zod";
import { withApplicationConnection } from "../../utils/ConnectionManager.js";
import type { DomainToolDefinition } from "../domainRuntime.js";

const GenericResponseSchema = z.object({}).passthrough();

const Point2DSchema = z.object({ x: z.number(), y: z.number() });
const WindowSchema = z.object({
  minX: z.number(),
  minY: z.number(),
  maxX: z.number(),
  maxY: z.number(),
});
const HandleSchema = z.string().regex(/^[0-9A-Fa-f]+$/, "Handles are hexadecimal strings, e.g. \"2A3F\".");
const SpaceSchema = z.string().min(1).describe("\"model\" (default) or a layout name.");

const CopyOperationSchema = z.object({
  mode: z.enum(["copy", "move"]).optional().describe("copy (default) duplicates the selection; move relocates it."),
  handles: z.array(HandleSchema).optional().describe("Entities to copy or move."),
  window: WindowSchema.optional().describe("Also select entities inside this box (in addition to handles)."),
  crossing: z.boolean().optional().describe("Window selection: true includes anything touching the box; false (default) only fully inside."),
  layers: z.array(z.string()).optional().describe("Window selection: only these layers."),
  types: z.array(z.string()).optional().describe("Window selection: only these DXF types, e.g. INSERT, LINE, MTEXT, MULTILEADER."),
  dx: z.number().describe("X displacement."),
  dy: z.number().describe("Y displacement."),
  space: SpaceSchema.optional().describe("Space the source entities live in."),
  targetSpace: SpaceSchema.optional().describe("Copy only: place copies in this space instead of the source space."),
  mirrorX: z.number().optional().describe("After the offset, mirror across the vertical line x = mirrorX. Text stays readable (justification flips, like MIRRTEXT 0)."),
});

const EditSchema = z.object({
  handle: HandleSchema,
  text: z.string().optional().describe("New text for TEXT, MTEXT (raw contents), MULTILEADER, ATTRIB, or dimension override."),
  attributes: z.record(z.string(), z.string()).optional().describe("Block attribute values by tag."),
  start: Point2DSchema.optional().describe("New start point (lines only)."),
  end: Point2DSchema.optional().describe("New end point (lines only)."),
  vertices: z.array(Point2DSchema).min(2).optional().describe("Replace all vertices of a line, polyline or leader."),
  colorIndex: z.number().int().min(0).max(256).optional().describe("ACI color: 0 = ByBlock, 256 = ByLayer."),
  linetype: z.string().optional().describe("Linetype name; must already be loaded in the drawing."),
  layer: z.string().optional(),
});

const QueryArgs = z.object({
  action: z.literal("query"),
  space: SpaceSchema.optional(),
  window: WindowSchema.optional(),
  crossing: z.boolean().optional(),
  layers: z.array(z.string()).optional(),
  types: z.array(z.string()).optional(),
  limit: z.number().int().min(1).max(5000).optional(),
  includeGeometry: z.boolean().optional(),
});
const CopyArgs = z.object({ action: z.literal("copy"), operations: z.array(CopyOperationSchema).min(1) });
const EditArgs = z.object({ action: z.literal("edit"), edits: z.array(EditSchema).min(1) });
const EraseArgs = z.object({ action: z.literal("erase"), handles: z.array(HandleSchema).min(1) });

const send = (method: string, payload: Record<string, unknown>) =>
  withApplicationConnection(async (appClient) => await appClient.sendCommand(method, payload));

export const ENTITY_DOMAIN_DEFINITION: DomainToolDefinition = {
  domain: "entity",
  actions: {
    query: {
      action: "query",
      inputSchema: QueryArgs,
      responseSchema: GenericResponseSchema,
      capabilities: ["query"],
      requiresActiveDrawing: true,
      safeForRetry: true,
      pluginMethods: ["queryEntities"],
      execute: async (args) => {
        const { action: _action, ...rest } = args as z.infer<typeof QueryArgs>;
        return await send("queryEntities", rest);
      },
    },
    copy: {
      action: "copy",
      inputSchema: CopyArgs,
      responseSchema: GenericResponseSchema,
      capabilities: ["create", "edit"],
      requiresActiveDrawing: true,
      safeForRetry: false,
      pluginMethods: ["copyEntities"],
      execute: async (args) => await send("copyEntities", { operations: (args as z.infer<typeof CopyArgs>).operations }),
    },
    edit: {
      action: "edit",
      inputSchema: EditArgs,
      responseSchema: GenericResponseSchema,
      capabilities: ["edit"],
      requiresActiveDrawing: true,
      safeForRetry: false,
      pluginMethods: ["editEntities"],
      execute: async (args) => await send("editEntities", { edits: (args as z.infer<typeof EditArgs>).edits }),
    },
    erase: {
      action: "erase",
      inputSchema: EraseArgs,
      responseSchema: GenericResponseSchema,
      capabilities: ["delete"],
      requiresActiveDrawing: true,
      safeForRetry: false,
      pluginMethods: ["eraseEntities"],
      execute: async (args) => await send("eraseEntities", { handles: (args as z.infer<typeof EraseArgs>).handles }),
    },
  },
  exposures: [
    {
      toolName: "civil3d_entity",
      displayName: "Civil 3D Entities",
      description:
        "Reads, copies, moves, edits and erases ordinary AutoCAD entities (blocks, lines, polylines, text, MText, multileaders, attributes) in model space or a layout. " +
        "query: list entities in a window with handles, block names, attribute values, text and geometry. " +
        "copy: batch copy or move entities by handles and/or window with a dx/dy offset and optional mirror; returns old-to-new handle maps. " +
        "edit: batch change text, attribute values, vertices/endpoints, color, linetype or layer by handle. " +
        "erase: delete entities by handle. Batch copy and edit work so one approval covers a whole detail.",
      inputShape: {
        action: z.enum(["query", "copy", "edit", "erase"]),
        space: SpaceSchema.optional(),
        window: WindowSchema.optional(),
        crossing: z.boolean().optional(),
        layers: z.array(z.string()).optional(),
        types: z.array(z.string()).optional(),
        limit: z.number().int().min(1).max(5000).optional(),
        includeGeometry: z.boolean().optional(),
        operations: z.array(CopyOperationSchema).optional(),
        edits: z.array(EditSchema).optional(),
        handles: z.array(HandleSchema).optional(),
      },
      supportedActions: ["query", "copy", "edit", "erase"],
      resolveAction: (rawArgs) => ({ action: String(rawArgs.action ?? ""), args: rawArgs }),
    },
  ],
};
