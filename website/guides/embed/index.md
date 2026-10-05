---
title: Embed a tutor
sidebar_label: Overview
description: Bring your PydanticAI Agent, register a Skilling course, and add a streaming tutor to your application.
slug: /embed
---

# Build a learning experience in your app

Give your users a course they can learn through conversation, inside your own product.
Skilling supplies the teaching flow, quizzes, feedback and durable learning record. Your
application supplies the interface, identity and model access.

Start with the [React reference application](quickstart.md), or mount the tutor directly
in an [existing FastAPI application](fastapi.md). Both use the same public Python integration.
The React app uses Vercel AI SDK to stream responses and renders structured learning state
alongside the conversation.

## Bring what you already have

| You bring | Skilling supplies |
|---|---|
| A PydanticAI Agent and your model credentials | Tutoring policy attached for each learner turn |
| A validated course folder | The current teaching material and legal course actions |
| Your signed-in user and course access rules | A separate durable learning session for each authorized learner and course |
| Your React components or another interface | A streaming FastAPI boundary and structured progress/feedback |
| Actual learner work and application evidence | Scoped informal review and explicit learner confirmation |

There is no Skilling account or hosted service to configure. The Python core remains usable
without PydanticAI, a provider SDK, or FastAPI.

## A tutor should feel like a conversation

The tutor can explain, ask questions and adapt its examples. Ordinary teaching continues after
the interface confirms it was shown. Readiness gates wait for the learner; quiz answers come
from the learner's choice. Canonical quiz feedback is displayed before moving on.

A model outage does not erase an action already saved. Reloading can recover the durable
learning position even when the conversation transcript is gone. The [operations guide](operate.md)
explains what persists, what a retry means, and the single-worker runtime boundary.

## Choose your starting point

1. [Run the React app](quickstart.md) with the included Welcome course.
2. [Mount the tutor in FastAPI](fastapi.md) using your own identity dependency.
3. [Build your React interface](react.md) around streamed text and learning state.
4. [Customize the Agent and evidence](customize.md) for your product.
5. [Plan deployment and recovery](operate.md) before deploying.

## Status

These are experimental source APIs for matching Skilling core 0.8.x and tutor 0.1.x.
Use the checkout installation in the quickstart; merging source does not publish packages.
The React app defaults to SQLite and can explicitly use file, PostgreSQL or S3 persistence.
The public `Tutor` also offers a file-backed convenience mode and a `session_factory` integration.
All modes currently require one application worker; durable storage does not coordinate chat or
display handles across replicas. The local demo does not provide production authentication.

The normative [specification](/spec) remains the authority for course and record semantics; the HTTP integration is an implementation API.
