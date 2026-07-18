# apps/web

Not yet implemented — this is build step 8 in [SPEC_VERSION.md](../../SPEC_VERSION.md)
"v1.0 Build Sequence," after the pipeline (steps 1-7) produces real output to
render. See [docs/08-ui-design.md](../../docs/08-ui-design.md) for the IA and
screen designs.

When this step starts: `npx create-next-app@latest` (App Router, TypeScript,
Tailwind) into this directory, then wire `shadcn/ui` per the design doc —
don't hand-roll scaffolding npx already does correctly.
