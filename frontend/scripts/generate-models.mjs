#!/usr/bin/env node

/**
 * generate-models.mjs
 *
 * Reads JSON Schema files from ../../models/profile/ and generates
 * a TypeScript file with Zod schemas + inferred types at models/profile.ts.
 *
 * Usage:  node scripts/generate-models.mjs
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MODELS_DIR = resolve(__dirname, '../../models/profile');
const OUT_FILE = resolve(__dirname, '../models/profile.ts');

// ── Read schemas ──────────────────────────────────────────────────────────────

function readSchema(name) {
  return JSON.parse(readFileSync(resolve(MODELS_DIR, name), 'utf-8'));
}

const base = readSchema('base.schema.json');
const create = readSchema('create.schema.json');
const update = readSchema('update.schema.json');
const publicSchema = readSchema('public.schema.json');
const privateSchema = readSchema('private.schema.json');

// ── Map a JSON Schema property to a Zod chain ────────────────────────────────

function propToZod(name, prop) {
  const parts = [];

  // Handle union types like ["string", "null"]
  const types = Array.isArray(prop.type) ? prop.type : [prop.type];
  const isNullable = types.includes('null');
  const primaryType = types.find((t) => t !== 'null') || 'string';

  switch (primaryType) {
    case 'string':
      if (prop.enum) {
        const stringLiterals = prop.enum.filter((v) => v !== null);
        const literals = stringLiterals.map((v) => JSON.stringify(v)).join(', ');
        parts.push(`z.enum([${literals}])`);
      } else {
        parts.push('z.string()');
        if (prop.minLength != null) parts.push(`.min(${prop.minLength})`);
        if (prop.maxLength != null) parts.push(`.max(${prop.maxLength})`);
        if (prop.pattern) parts.push(`.regex(/${prop.pattern}/)`);
        if (prop.format === 'date') parts.push(`.regex(/^\\d{4}-\\d{2}-\\d{2}$/)`);
      }
      break;
    case 'number':
    case 'integer':
      parts.push('z.number()');
      if (primaryType === 'integer') parts.push('.int()');
      if (prop.minimum != null) parts.push(`.min(${prop.minimum})`);
      if (prop.maximum != null) parts.push(`.max(${prop.maximum})`);
      break;
    case 'boolean':
      parts.push('z.boolean()');
      break;
    case 'array': {
      let itemZod;
      if (prop.items?.enum) {
        const literals = prop.items.enum.map((v) => JSON.stringify(v)).join(', ');
        itemZod = `z.enum([${literals}])`;
      } else {
        const itemType = prop.items?.type || 'string';
        itemZod = `z.${itemType}()`;
        if (prop.items?.maxLength != null) itemZod += `.max(${prop.items.maxLength})`;
      }
      parts.push(`z.array(${itemZod})`);
      if (prop.maxItems != null) parts.push(`.max(${prop.maxItems})`);
      break;
    }
    default:
      parts.push('z.unknown()');
  }

  if (isNullable) parts.push('.nullable()');
  if (prop.default !== undefined) {
    const defaultVal =
      prop.default === null ? 'null' : JSON.stringify(prop.default);
    parts.push(`.default(${defaultVal})`);
  }

  return parts.join('');
}

// ── Resolve $ref to base property ─────────────────────────────────────────────

function resolveRef(ref) {
  // e.g. "base.schema.json#/properties/username"
  const match = ref.match(/#\/properties\/(.+)$/);
  if (!match) throw new Error(`Cannot resolve $ref: ${ref}`);
  const propName = match[1];
  const prop = base.properties[propName];
  if (!prop) throw new Error(`Property "${propName}" not found in base schema`);
  return { name: propName, prop };
}

// ── Build a Zod object schema string from a schema definition ─────────────────

function schemaToZod(schema, schemaName) {
  const lines = [];
  const props = schema.properties || {};
  const required = new Set(schema.required || []);

  for (const [key, value] of Object.entries(props)) {
    let propName = key;
    let propDef = value;

    // Resolve $ref
    if (value.$ref) {
      const resolved = resolveRef(value.$ref);
      propName = resolved.name;
      propDef = resolved.prop;
    }

    let zodStr = propToZod(propName, propDef);

    // Make optional if not required
    if (!required.has(propName)) {
      zodStr += '.optional()';
    }

    lines.push(`  ${propName}: ${zodStr},`);
  }

  let chain = `z.object({\n${lines.join('\n')}\n})`;

  if (schema.minProperties != null) {
    // For update schema — at least one field must be provided.
    // We use .refine() since Zod doesn't have minProperties natively.
    chain += `.refine(\n  (data) => Object.keys(data).filter((k) => data[k as keyof typeof data] !== undefined).length >= ${schema.minProperties},\n  { message: 'At least ${schema.minProperties} field(s) must be provided' }\n)`;
  }

  return chain;
}

// ── Generate the output file ──────────────────────────────────────────────────

const header = `// ──────────────────────────────────────────────────────────────────────────────
// AUTO-GENERATED — DO NOT EDIT
// Source: models/profile/*.schema.json
// Regenerate: npm run generate:models
// ──────────────────────────────────────────────────────────────────────────────

import { z } from 'zod';

export type FieldMeta = {
  name: string;
  label: string;
  placeholder: string;
  type: 'string' | 'number' | 'boolean';
  required: boolean;
  nullable: boolean;
  keyboard: 'default' | 'email-address' | 'numeric' | 'phone-pad';
  secure: boolean;
  multiline: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  description?: string;
};
`;

// ── Build field metadata array for a schema ───────────────────────────────────

function toLabel(name) {
  // camelCase → Title Case: "displayName" → "Display Name"
  return name
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (s) => s.toUpperCase())
    .trim();
}

function inferKeyboard(prop, name) {
  if (name.toLowerCase().includes('email')) return 'email-address';
  if (name.toLowerCase().includes('phone')) return 'phone-pad';
  const types = Array.isArray(prop.type) ? prop.type : [prop.type];
  const primary = types.find((t) => t !== 'null') || 'string';
  if (primary === 'number' || primary === 'integer') return 'numeric';
  return 'default';
}

function inferPlaceholder(prop, name) {
  return `Enter ${toLabel(name).toLowerCase()}`;
}

function buildFieldsMeta(schema) {
  const props = schema.properties || {};
  const required = new Set(schema.required || []);
  const fields = [];

  for (const [key, value] of Object.entries(props)) {
    let propName = key;
    let propDef = value;

    if (value.$ref) {
      const resolved = resolveRef(value.$ref);
      propName = resolved.name;
      propDef = resolved.prop;
    }

    const types = Array.isArray(propDef.type) ? propDef.type : [propDef.type];
    const isNullable = types.includes('null');
    const primaryType = types.find((t) => t !== 'null') || 'string';
    const mappedType = (primaryType === 'integer') ? 'number' : primaryType;

    const meta = {
      name: propName,
      label: toLabel(propName),
      placeholder: inferPlaceholder(propDef, propName),
      type: mappedType,
      required: required.has(propName),
      nullable: isNullable,
      keyboard: inferKeyboard(propDef, propName),
      secure: false,
      multiline: (propDef.maxLength || 0) > 200,
    };

    if (propDef.minLength != null) meta.minLength = propDef.minLength;
    if (propDef.maxLength != null) meta.maxLength = propDef.maxLength;
    if (propDef.pattern) meta.pattern = propDef.pattern;
    if (propDef.description) meta.description = propDef.description;

    fields.push(meta);
  }

  return fields;
}

function fieldsMetaToString(fields, exportName) {
  const items = fields.map((f) => {
    const entries = Object.entries(f)
      .map(([k, v]) => `    ${k}: ${JSON.stringify(v)},`)
      .join('\n');
    return `  {\n${entries}\n  }`;
  });
  return `export const ${exportName}: FieldMeta[] = [\n${items.join(',\n')}\n];`;
}

const sections = [];

// Extract constants from base schema for UI usage
const interestsEnum = base.properties.interests?.items?.enum;
const fitnessLevelEnum = base.properties.fitnessLevel?.enum?.filter((v) => v !== null);

if (interestsEnum) {
  sections.push(`export const INTEREST_OPTIONS = ${JSON.stringify(interestsEnum, null, 2)} as const;`);
}
if (fitnessLevelEnum) {
  sections.push(`export const FITNESS_LEVEL_OPTIONS = ${JSON.stringify(fitnessLevelEnum, null, 2)} as const;`);
}

// Base
sections.push(`/** ${base.description} */
export const BaseProfileSchema = ${schemaToZod(base, 'BaseProfile')};
export type BaseProfile = z.infer<typeof BaseProfileSchema>;`);

// Create
sections.push(`/** ${create.description} */
export const CreateProfileSchema = ${schemaToZod(create, 'CreateProfile')};
export type CreateProfile = z.infer<typeof CreateProfileSchema>;`);
sections.push(fieldsMetaToString(buildFieldsMeta(create), 'CreateProfileFields'));

// Update
sections.push(`/** ${update.description} */
export const UpdateProfileSchema = ${schemaToZod(update, 'UpdateProfile')};
export type UpdateProfile = z.infer<typeof UpdateProfileSchema>;`);
sections.push(fieldsMetaToString(buildFieldsMeta(update), 'UpdateProfileFields'));

// Public
sections.push(`/** ${publicSchema.description} */
export const PublicProfileSchema = ${schemaToZod(publicSchema, 'PublicProfile')};
export type PublicProfile = z.infer<typeof PublicProfileSchema>;`);

// Private
sections.push(`/** ${privateSchema.description} */
export const PrivateProfileSchema = ${schemaToZod(privateSchema, 'PrivateProfile')};
export type PrivateProfile = z.infer<typeof PrivateProfileSchema>;`);

const output = [header, ...sections].join('\n\n') + '\n';

// Write
mkdirSync(dirname(OUT_FILE), { recursive: true });
writeFileSync(OUT_FILE, output, 'utf-8');

console.log(`✅ Generated ${OUT_FILE}`);
