- having in mind the requirements in @attachment:pcb-parts-picking-ai-framework-summary.md, how can we build a harness to help us with this?

- ignore this is for a workshop. Imagine this will be an internal tool used by eletrical engineers.
With that in mind, discuss the implementation steps with me and start create resources we can hand to agents to build the solution

- create an evidence summary of this whole conversation and store it in a md file so it can be used later

- create prompts for each phase that call the appropriate agent. Build a factory process that stops after each Milestone, asks for review, and handsover to the next milestone prompt

- which agent should I use to implement each phase of the roadmap

- create prompts for each phase that call the appropriate agent. Build a factory process that stops after each Milestone, asks for review, and handsover to the next milestone prompt

- /roadmap-m0-contracts-skeleton

- create an evidence summary of this whole conversation and store it in a md file so it can be used later

- use the decision log

- /roadmap-m1-ingest

- update the agents that make sense to subagents so they can be called inside the prompts

- /roadmap-m2-normalize-classify

- /roadmap-m3-policy

- append an evidence summary of this whole conversation and store it in the #attachment:decision-log.md

- /roadmap-m4-sourcing-fixtures

- append an evidence summary of this whole conversation and store it in the #attachment:decision-log.md

- /roadmap-m5-planning-export

- append an evidence summary of this whole conversation and store it in the #attachment:decision-log.md

- /roadmap-m6-web-app

- append an evidence summary of this whole conversation and store it in the #attachment:decision-log.md

- /roadmap-m7-live-adapters

- append an evidence summary of this whole conversation and store it in the #attachment:decision-log.md

- /roadmap-m8-evals-hardening

- append an evidence summary of this whole conversation and store it in the #attachment:decision-log.md

- /roadmap-m8-evals-hardening

- Create a readme explaining the purpose of the app and how to use it and place it the root of the repo

- all the 8 phases in the plan where executed, why do you say "This is an in-progress project built milestone-by-milestone; see
docs/roadmap.md for the full plan. As of now, the pipeline runner
wires up ingest and normalize; later stages (policy, sourcing, planning,
exporters) exist as modules with their own tests but are not yet chained into the
end-to-end run."

what is missing?