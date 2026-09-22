# AI Framework for PCB Parts Picking

## Purpose

The goal is to build an AI-assisted framework that helps transform a PCB bill of materials into realistic purchasing options. The system should not fully replace human judgment; instead, it should guide component selection, compare suppliers, and produce structured outputs that make procurement easier and more transparent.

## Core Idea

The workflow starts with the output from a PCB design or assembly tool, such as a CSV or similar export containing the required components. That input is then preprocessed into a structured requirements list. From there, the system classifies parts by type, applies compatibility rules, checks supplier catalogs, and produces candidate parts with explanations.

## Proposed Framework

1. Parse the PCB output into a normalized parts list.
2. Separate components by category, since resistors, capacitors, and other part types follow different selection rules.
3. Query supplier knowledge bases or catalogs for availability, lead time, and pricing.
4. Use agents to generate candidate parts and justify why each option is a fit.
5. Compare purchasing strategies across suppliers to optimize for cost, delivery time, and convenience.
6. Export the final recommendation in supplier-friendly formats such as CSV or Excel import files.

## Supplier and Data Considerations

The discussion highlighted common suppliers such as Mouser, DigiKey, and Farnell. A key implementation idea is to leverage their digital catalogs and BOM import features so the framework can output files in the format each supplier already accepts. At the same time, catalog freshness is a major challenge because part availability changes frequently, so the system must treat stock data as volatile.

## Decision Logic

The framework should support multiple decision modes rather than forcing a single answer. For example, it should be able to recommend:

- the cheapest overall order,
- the most convenient order from a delivery perspective,
- the best split order across multiple suppliers,
- the best compromise between price and availability.

This gives the user a report of options instead of a single rigid recommendation, which is more useful when trade-offs matter.

## Workshop Approach

The workshop should be guided and structured so participants stay focused on the same problem. The intended flow is:

1. Introduce the key concepts: agents, skills, instructions, and harnesses.
2. Present the problem statement and the real-world PCB purchasing context.
3. Build the solution in stages, starting from input parsing and ending with supplier-aware output.
4. Encourage participants to ask the AI how it would solve the problem before writing code.

The emphasis is on learning the concepts and seeing what is possible with AI-assisted development, not on delivering a production-ready procurement platform.

## Important Constraints

- Supplier catalogs may be incomplete or outdated.
- Inventory and part counts can change quickly.
- Filtering and search behavior on supplier sites can be inconsistent.
- Human review is still needed before final purchasing decisions.

## Desired Outcome

The project should demonstrate a practical AI workflow for PCB parts selection: ingest requirements, reason about compatibility, search supplier data, compare options, and generate exportable purchasing lists. The result should be a strong educational prototype that can later evolve into a production tool.