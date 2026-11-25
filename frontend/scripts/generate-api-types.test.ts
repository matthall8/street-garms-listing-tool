// @vitest-environment  node
import { expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { generateApiTypes } from './generate-api-types';


test("API Types are fresh", async() => {
    const openApiFile = readFileSync(new URL("./../openapi.json", import.meta.url), 'utf8');
    const parsedFile = JSON.parse(openApiFile);
    const apiTypes = await generateApiTypes(parsedFile);
    const savedApiTypes = readFileSync(new URL("./../src/api-schema.ts", import.meta.url), 'utf8');
    expect(apiTypes).toBe(savedApiTypes);
})