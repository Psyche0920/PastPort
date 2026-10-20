---
name: code-reviewer
description: Guidelines to for code writing and reviews, inspired by the Karpathy guidelines, to avoid overcomplicated solutions and inefficient refactoring. 
version: 1.0.0
---

## 1. Core Architecture & Security
- Write and review code using Object-Oriented Programming (OOP) in Python and SOLID principles.
- Keep code lines short without stripping functionality.
- Never read `.env` files. Absolutely never log, expose, or commit `.env` contents.

## 2. Think Before Coding
- State your assumptions explicitly. If something is unclear or uncertain, stop, and ask.
- If multiple interpretations exist, present them, don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.

## 3. Simplicity First
- No features beyond what was asked.
- No abstractions for single-use code.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify it.

## 4. Surgical Changes
- Touch only what you must. Clean up only your own mess.
- Don't refactor existing code that isn't broken.
- Match existing style, even if you'd do it differently.
- Remove imports, variables, and functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless explicitly asked; mention it instead.
- Every changed line should trace directly to the user's request.

## 5. Skills available and when to use