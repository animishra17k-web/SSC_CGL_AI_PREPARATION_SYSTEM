# AI Layer Contracts

Each layer has one job. Do not ask one giant prompt to do everything.

## L0 ORCHESTRATOR
Decides which layer runs next and passes only required context.

## L1 INGEST
Input: raw source.
Output: normalized text + metadata + source locations.

## L2 EXTRACT
Input: normalized source.
Output: atomic concepts/rules/formulas/facts + source references.

## L3 TEACH
Input: extracted knowledge + learner level.
Output: master notes + question-pattern map + traps.

## L4 FLASHCARD
Input: atomic knowledge + notes.
Output: concise recall cards.

## L5 QUESTION
Input: knowledge + question patterns + learner level.
Output: exam-style questions across supported difficulty/types.

## L6 VALIDATE
Input: generated notes/cards/questions.
Output: errors, unsupported claims, ambiguity, duplicate questions.

## L7 TEST
Input: selected questions.
Output: test session and answers.

## L8 EVALUATE
Input: questions + learner answers.
Output: correctness + error classification + weakness signals.

## L9 ADAPT
Input: evaluation + historical learning state.
Output: updated mastery/weakness/revision priority + repair actions.

## L10 REVIEW
Input: current learning state.
Output: today's due topics/cards/questions.

The critical engineering rule is:
A layer must not pretend it knows information that is not in its input.
