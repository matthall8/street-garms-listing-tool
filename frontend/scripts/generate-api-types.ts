import openapiTS, { astToString, COMMENT_HEADER, type OpenAPI3 } from "openapi-typescript";
import { readFileSync, writeFileSync } from 'node:fs';

export async function generateApiTypes(schema: OpenAPI3): Promise<string> {
  const ast = await openapiTS(schema);
  return COMMENT_HEADER + astToString(ast);
}


if (import.meta.main) {
  const openApiFile = readFileSync(new URL("./../openapi.json", import.meta.url), 'utf8');
  const parsedFile = JSON.parse(openApiFile);
  const apiTypes = await generateApiTypes(parsedFile)
  writeFileSync(new URL("./../src/api-schema.ts", import.meta.url), apiTypes);
}