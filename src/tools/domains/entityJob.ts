import { createHash } from "node:crypto";
import { readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";

/**
 * Entity jobs: one JSON document that describes a whole batch of copies, edits
 * and erases. Edits and erases may reference entities that the same job copies
 * ("ref": "<copyId>:<sourceHandle>"), so a drawing detail can be built in one
 * tool call without a round trip to learn the new handles.
 *
 * Job format (version 1):
 * {
 *   "version": 1,
 *   "copies": [{ "id": "p1", "handles": ["2A4BC2"], "dx": 10, "dy": 0, "mirrorX": 5, "mode": "copy" }],
 *   "edits":  [{ "ref": "p1:2A4BC2", "text": "NEW" }, { "handle": "1F00", "colorIndex": 1 }],
 *   "erase":  ["1F01", { "ref": "p1:2A4BC3" }]
 * }
 */

export const MAX_JOB_FILE_BYTES = 8 * 1024 * 1024;

type JsonObject = Record<string, unknown>;
export type SendFn = (method: string, payload: JsonObject) => Promise<unknown>;

export interface EntityJobCopy extends JsonObject {
  id: string;
}

export interface EntityJob {
  version?: number;
  copies?: EntityJobCopy[];
  edits?: JsonObject[];
  erase?: Array<string | { ref?: string; handle?: string }>;
}

export class EntityJobError extends Error {
  public readonly code = "CIVIL3D.INVALID_INPUT";
}

function jobError(message: string): EntityJobError {
  return new EntityJobError(message);
}

export function resolveJobFilePath(jobFile: string): string {
  if (!path.isAbsolute(jobFile)) {
    throw jobError(`jobFile must be an absolute path: '${jobFile}'.`);
  }
  if (path.extname(jobFile).toLowerCase() !== ".json") {
    throw jobError("jobFile must be a .json file.");
  }
  return path.resolve(jobFile);
}

export function readJobFile(jobFile: string): { path: string; text: string; sha256: string } {
  const resolved = resolveJobFilePath(jobFile);
  const stats = statSync(resolved);
  if (!stats.isFile()) {
    throw jobError(`jobFile is not a file: '${resolved}'.`);
  }
  if (stats.size > MAX_JOB_FILE_BYTES) {
    throw jobError(`jobFile is larger than ${MAX_JOB_FILE_BYTES} bytes.`);
  }
  const text = readFileSync(resolved, "utf8");
  return { path: resolved, text, sha256: sha256(text) };
}

export function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

/** SHA-256 of the job file named by parameters.jobFile, or undefined when there is none. */
export function jobFileDigest(parameters: JsonObject): string | undefined {
  if (typeof parameters.jobFile !== "string" || parameters.jobFile.length === 0) {
    return undefined;
  }
  return readJobFile(parameters.jobFile).sha256;
}

export function parseJob(text: string): EntityJob {
  let job: unknown;
  try {
    job = JSON.parse(text.replace(/^﻿/, ""));
  } catch (error) {
    throw jobError(`Job file is not valid JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
  return validateJob(job);
}

export function validateJob(job: unknown): EntityJob {
  if (!job || typeof job !== "object" || Array.isArray(job)) {
    throw jobError("Job must be a JSON object.");
  }
  const value = job as EntityJob;
  if (value.version !== undefined && value.version !== 1) {
    throw jobError(`Unsupported job version ${String(value.version)}; expected 1.`);
  }
  for (const key of ["copies", "edits", "erase"] as const) {
    if (value[key] !== undefined && !Array.isArray(value[key])) {
      throw jobError(`Job '${key}' must be an array.`);
    }
  }

  const ids = new Set<string>();
  (value.copies ?? []).forEach((copy, index) => {
    if (!copy || typeof copy !== "object") throw jobError(`copies[${index}] must be an object.`);
    if (typeof copy.id !== "string" || copy.id.length === 0 || copy.id.includes(":")) {
      throw jobError(`copies[${index}].id must be a non-empty string without ':'.`);
    }
    if (ids.has(copy.id)) throw jobError(`Duplicate copy id '${copy.id}'.`);
    ids.add(copy.id);
    if (typeof copy.dx !== "number" || typeof copy.dy !== "number") {
      throw jobError(`copies[${index}] ('${copy.id}') needs numeric dx and dy.`);
    }
    if (!Array.isArray(copy.handles) && !copy.window) {
      throw jobError(`copies[${index}] ('${copy.id}') needs handles or a window.`);
    }
  });

  const checkRef = (ref: unknown, where: string) => {
    if (typeof ref !== "string") throw jobError(`${where}.ref must be a string.`);
    const [id, handle] = splitRef(ref, where);
    if (!ids.has(id)) throw jobError(`${where}.ref '${ref}' names unknown copy id '${id}'.`);
    if (!/^[0-9A-Fa-f]+$/.test(handle)) throw jobError(`${where}.ref '${ref}' has an invalid handle.`);
  };

  (value.edits ?? []).forEach((edit, index) => {
    if (!edit || typeof edit !== "object") throw jobError(`edits[${index}] must be an object.`);
    const hasHandle = typeof edit.handle === "string";
    const hasRef = edit.ref !== undefined;
    if (hasHandle === hasRef) throw jobError(`edits[${index}] needs exactly one of handle or ref.`);
    if (hasRef) checkRef(edit.ref, `edits[${index}]`);
  });

  (value.erase ?? []).forEach((entry, index) => {
    if (typeof entry === "string") return;
    if (!entry || typeof entry !== "object") throw jobError(`erase[${index}] must be a handle or {ref}.`);
    if (entry.ref !== undefined) checkRef(entry.ref, `erase[${index}]`);
    else if (typeof entry.handle !== "string") throw jobError(`erase[${index}] needs handle or ref.`);
  });

  return value;
}

function splitRef(ref: string, where: string): [string, string] {
  const at = ref.lastIndexOf(":");
  if (at <= 0 || at === ref.length - 1) {
    throw jobError(`${where}.ref '${ref}' must look like '<copyId>:<sourceHandle>'.`);
  }
  return [ref.slice(0, at), ref.slice(at + 1)];
}

export type HandleMaps = Record<string, Record<string, string>>;

export function resolveRef(ref: string, maps: HandleMaps, where: string): string {
  const [id, source] = splitRef(ref, where);
  const map = maps[id];
  if (!map) throw jobError(`${where}: copy '${id}' produced no handle map.`);
  const resolved = map[source.toUpperCase()];
  if (!resolved) {
    throw jobError(`${where}: copy '${id}' did not copy source handle '${source}'.`);
  }
  return resolved;
}

function upperKeys(map: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (map && typeof map === "object") {
    for (const [key, value] of Object.entries(map as Record<string, unknown>)) {
      out[key.toUpperCase()] = String(value);
    }
  }
  return out;
}

export interface EntityJobResult extends JsonObject {
  status: "completed" | "failed";
  stage: "copy" | "edit" | "erase" | "done";
  copies: Record<string, number>;
  copiedEntities: number;
  edited: number;
  erased: number;
  error?: string;
  handles?: HandleMaps;
}

/**
 * Runs a job against the plugin: one copyEntities call, then one editEntities
 * call with refs resolved to new handles, then one eraseEntities call. Each
 * stage is its own drawing transaction; if a later stage fails, the result
 * still carries the handle maps of what was already created.
 */
export async function runEntityJob(job: EntityJob, send: SendFn): Promise<EntityJobResult> {
  const result: EntityJobResult = {
    status: "completed",
    stage: "copy",
    copies: {},
    copiedEntities: 0,
    edited: 0,
    erased: 0,
  };
  const maps: HandleMaps = {};
  result.handles = maps;

  try {
    const copies = job.copies ?? [];
    if (copies.length > 0) {
      const operations = copies.map(({ id: _id, ...operation }) => operation);
      const response = await send("copyEntities", { operations }) as { operations?: Array<{ index?: number; handles?: unknown }> };
      const results = response?.operations ?? [];
      if (results.length !== copies.length) {
        throw new Error(`copyEntities returned ${results.length} results for ${copies.length} operations.`);
      }
      results.forEach((entry, position) => {
        const copy = copies[entry.index ?? position];
        const map = upperKeys(entry.handles);
        maps[copy.id] = map;
        result.copies[copy.id] = Object.keys(map).length;
        result.copiedEntities += Object.keys(map).length;
      });
    }

    result.stage = "edit";
    const edits = (job.edits ?? []).map((edit, index) => {
      const { ref, ...rest } = edit;
      return typeof ref === "string"
        ? { ...rest, handle: resolveRef(ref, maps, `edits[${index}]`) }
        : rest;
    });
    if (edits.length > 0) {
      const response = await send("editEntities", { edits }) as { edits?: unknown[] };
      result.edited = response?.edits?.length ?? edits.length;
    }

    result.stage = "erase";
    const erase = (job.erase ?? []).map((entry, index) => {
      if (typeof entry === "string") return entry;
      return typeof entry.ref === "string"
        ? resolveRef(entry.ref, maps, `erase[${index}]`)
        : String(entry.handle);
    });
    if (erase.length > 0) {
      const response = await send("eraseEntities", { handles: erase }) as { count?: number };
      result.erased = response?.count ?? erase.length;
    }

    result.stage = "done";
  } catch (error) {
    result.status = "failed";
    result.error = error instanceof Error ? error.message : String(error);
  }

  return result;
}

export function resultFilePath(jobPath: string): string {
  return jobPath.replace(/\.json$/i, ".result.json");
}

export function writeJobResult(jobPath: string, result: EntityJobResult, jobSha256: string): string {
  const target = resultFilePath(jobPath);
  writeFileSync(target, JSON.stringify({ jobFile: jobPath, jobSha256, ...result }, null, 2), "utf8");
  return target;
}
