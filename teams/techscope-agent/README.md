# TechScope Teams Agent Prototype

## Purpose

Microsoft Teams SDK v2 TypeScript adapter for the existing TechScope FastAPI service.

Flow:

Teams message
→ `@microsoft/teams.apps`
→ `techscope-client.ts`
→ `POST {TECHSCOPE_API_BASE_URL}/ask`
→ TechScope FastAPI
→ grounded answer / citations / technology IDs
→ Teams reply

## Status

Prototype only.

The package proves:
- Teams SDK source implementation
- TypeScript compilation
- HTTP adapter execution
- `/ask` request forwarding
- grounded answer formatting
- citation formatting
- technology-ID formatting

It does **not** claim:
- Teams tenant registration
- deployed Teams app
- live Teams message E2E
- production authentication

## Runtime setting

`TECHSCOPE_API_BASE_URL`

Default:

`http://127.0.0.1:8000`

## SDK policy

Uses `@microsoft/teams.apps` from Teams SDK v2.

TeamsFx is intentionally not used.
