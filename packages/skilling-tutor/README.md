# Skilling tutor

Experimental optional conversational Pydantic AI tutor for trusted
Python producers. Requires matching Skilling core 0.8.x, Pydantic AI slim 2.52.x and
Harness skills 0.52.x. Shares the exact bundled learn/progress/homework policy and references
through native skill activation and one allowlisted reference reader. `SkillingRunner.chat`
accepts the latest learner message, fresh safe context and producer-owned history, returning
a reply, optional validated informal feedback and a copied full transcript. Advanced scoped
APIs and direct native Agent composition remain available.
Provider SDKs are producer-selected extras; this package supplies no provider default,
mutation tools, console command or automatic tracing. No public release is claimed.

See [the producer guide](https://github.com/futureofdev/skilling/blob/main/docs/python-tutor.md)
for direct Agent composition, structured informal advice, history and usage ownership.

Licensed under Apache-2.0. Includes a `py.typed` marker.
