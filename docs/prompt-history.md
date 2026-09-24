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

- create me a prompt that runs the setup for the project mentioned in this readme

- review the prompt because there are deprecated tools.
Also, check if UV is installed. it is worth installing if not present

- /setup-project

- what does "normalize_fallback did not produce a usable result: no LLM client configured" mean

- how can I pass the real client and where is that stated in the readme file?

- before you do that, what is my best option? I have github copilot subscription. But none other

- yes, go with Ollama

- did you update the code to use the ollama llm? I still see the api key option in the login.
Can you also ensure Ollama is running when starting the project and start it if it is not?

- create a startup script that sets the env var, and launches both backend and frontend

- I want ollama to run in a docker image, and to be started as part of the startup script

- is there a management ui for ollama

- can you aslo install that as part of the start script

- write all the prompts I used to #attachment:prompt-history.md 