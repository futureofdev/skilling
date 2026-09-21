# Example courses

## Start here: `welcome-skilling`

[Welcome to Skilling](welcome-skilling/) is a short learner orientation. It teaches the
explain → question → revisit loop and helps the learner preserve a goal, takeaway and next
action in their showcase.

After package and tag publication, start it with:

```bash
skilling start 'gh:futureofdev/skilling@v0.6.0#examples/welcome-skilling' my-learning --json
```

## Learn the format: `hello-skilling`

[hello-skilling](hello-skilling/) is a small course about the Skilling format itself. Authors
can read it alongside the [authoring guide](../docs/authoring-a-course.md).

```bash
skilling validate examples/hello-skilling --strict
```

## Exercise every surface: `workbench`

[workbench](workbench/) is a practical files, folders and Git course. It assumes the learner
can use a local shell and Git. It covers structured objectives, declared absences, badges,
ceremony, assets, homework and observable practice in a compact course.

```bash
skilling validate examples/workbench --strict
```

Repository tests keep all three examples conforming. `welcome-skilling` is the learner front
door, `hello-skilling` is the readable format example, and `workbench` is the exercising
fixture; none is a bundled catalogue inside the PyPI package.
