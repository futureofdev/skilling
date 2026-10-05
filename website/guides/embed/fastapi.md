---
title: Mount the tutor in FastAPI
sidebar_label: FastAPI integration
description: Add a Skilling tutor to your existing application with your own Agent and authentication.
---

# Mount the tutor in FastAPI

Create one `Tutor` for your application process. Register course directories explicitly and
use your existing FastAPI authentication dependency to supply a stable learner identity.

```python
import os
from pathlib import Path

from fastapi import FastAPI
from pydantic_ai import Agent

from my_app.auth import current_user
from skilling_tutor import Tutor
from skilling_tutor.fastapi import mount_tutor

app = FastAPI()
agent = Agent(
    os.environ["TUTOR_MODEL"],
    instructions="Be warm, concise, and adapt examples to the learner.",
)
tutor = Tutor(
    agent=agent,
    courses={"onboarding": Path("./courses/onboarding")},
    state_dir=Path("./data/learning"),
)
mount_tutor(
    app,
    tutor,
    prefix="/api/learn",
    current_user=current_user,
)
```

`current_user` is application code: in this simplest form it returns a stable, nonempty user
ID after authentication. The browser does not choose that identity. Install matching source
packages and a provider SDK as shown in the [quickstart](quickstart.md). FastAPI support is an
optional `skilling-tutor[fastapi]` extra.

Course aliases such as `onboarding` are route names. The registered directory must contain a
valid Skilling course. Keep that course version fixed while the application serves it; an
existing record is never silently upgraded to different course content.

## Use your existing user object

Map your authenticated principal to its durable application identifier and check entitlement
before any course read or write:

```python
mount_tutor(
    app,
    tutor,
    prefix="/api/learn",
    current_user=current_user,
    learner_id=lambda user: user.id,
    authorize=lambda user, course: course in user.allowed_courses,
)
```

Use an opaque account ID, not a display name that can change. Use collision-free tenant/account identity when tenants can reuse local IDs; with a producer-owned
`Session`, also choose an explicit trusted `SessionScope.namespace`. Keep your existing application auth and
session protections in place. The mount supplies neither accounts nor login screens.

## Own the interface, reuse the teaching flow

The mounted routes expose current learning state, chat streaming, rendering acknowledgement,
and explicit learner operations. The [React integration](react.md) shows their request and
event shapes. Request IDs identify retries of one learner operation; create a new ID for a
new operation. A stale display is a conflict, so refresh state before offering another action.

Only acknowledge a completed teaching or canonical feedback display after rendering it. Reading
state, receiving tokens, and a model claiming something was shown are not presentation receipts.
This distinction lets the runtime continue ordinary teaching automatically while preserving
learner decisions at gates and quizzes.

## Connect your persistence

The `state_dir` example above is the file-backed convenience mode. For SQLite, PostgreSQL or S3,
provide a synchronous `session_factory` that opens a scoped `Session` using the store your
application owns. Pass `session_factory` **instead of** `state_dir`:

```python
from skilling.session import Session
from skilling.store import SessionScope

# store is opened during application startup and closed during shutdown.
# authorized_work_root is your application's permission-checked work-directory lookup.
def open_learning_session(learner_id, course_alias, course):
    return Session.open(
        course.root,
        store=store,
        scope=SessionScope("your-product", learner_id, course.id),
        work_root=authorized_work_root(learner_id, course_alias),
    )

tutor = Tutor(
    agent=agent,
    courses={"onboarding": Path("./courses/onboarding")},
    session_factory=open_learning_session,
)
```

Authentication and `authorize` run before the mount resolves the tutor session. The factory's
arguments are trusted application identity, the route alias and the registered `Course`, never
model-selected paths. The store scope uses `course.id` from the course manifest, not the HTTP alias.
Make the work-root lookup enforce the same identity/course permission. The
[session reference](/reference/embedding-a-tutor#open-a-scoped-session) shows the concrete store
constructor and explains synchronous calls, opaque revisions and captured action handles.

## Process and storage lifetime

Run one application worker in every persistence mode. The `Tutor` owns in-process locks,
conversation history and presentation receipts. Multiple workers or replicas do not share those
values, even when they use the same database. See [deployment and recovery](operate.md) before
changing the deployment topology.

The application owns any model-provider HTTP clients it creates. Open and close those clients
in your normal FastAPI lifespan. `Tutor` uses the Agent you supply and does not take ownership
of external connections or turn on tracing.

## HTTP and authentication failures

The mount expects JSON writes and checks the browser origin. If your frontend uses another
origin, set `allowed_origins` to the exact trusted origins and configure your application's CORS
middleware and credential policy too. Origin checks do not replace authentication or your
application's session/CSRF protections. Never expose a learner-selector dependency as login.

Return an authentication failure from `current_user` for expired sessions. Use `authorize` to
deny course access before any state read, and avoid shared caches for personalized state or
streams. The [React contract](react.md#http-surface) documents request bodies and presentation
acknowledgements. Keep provider errors useful to the learner without returning credentials,
raw backend exceptions or private filesystem paths.
