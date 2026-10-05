# Browser tutor walkthrough

The Python-rendered browser example has been replaced by the
[React tutor application](../examples/react-tutor/README.md). Its Python backend uses the public
`Tutor` runtime and FastAPI adapter; the frontend streams conversation and displays structured
learning state with React and Vercel AI SDK.

Start with the [React quickstart](https://futureofdev.github.io/skilling/docs/embed/quickstart).
For an existing product, follow the
[FastAPI integration guide](https://futureofdev.github.io/skilling/docs/embed/fastapi), then
[React rendering and acknowledgements](https://futureofdev.github.io/skilling/docs/embed/react).
The [session integration reference](embedding-a-tutor.md) covers persistent backend configuration,
trusted identity and recovery. The [lower-level tutor API](python-tutor.md) remains available
for applications that own their conversation loop.

These are source-checkout instructions. The local demo identity is not production authentication;
replace it with your application's verified identity and course authorization before hosting.
