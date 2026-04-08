Gemma-4 "felt" like it was reading because it was actually trying to build a mental model, which is why it hit the context limit.

 ### The Solution: The "Decomposition" Strategy

 Instead of asking the agent to "Read the code and write the SDK," you must break this into a multi-stage pipeline. You need to separate
 Discovery from Design from Implementation.

 Here is the exact workflow you should use with me (or any agent) to get that Python SDK skeleton:

 #### Stage 1: The "Knowledge Extraction" Phase (Building the Map)

 Do not ask for code yet. Ask for a "System Map."
 - Prompt: "I want to build a Python SDK for this Go application. First, I don't want any code. I want you to explore the Go codebase and
 create a high-level 'Logic Map.' Identify: 1. The primary entry points (APIs/CLI), 2. The core data structures (the 'Models'), and 3. The
 lifecycle of a request/command. Use ls, grep, and read to build this map. Output it as a Markdown summary."
 - Goal: This forces the model to use its tools to build a compressed version of the logic in its own "memory" without filling the context
 with raw code yet.

 #### Stage 2: The "Interface Definition" Phase (The Contract)

 Once you have the map, define the "Contract."
 - Prompt: "Based on the Logic Map we just created, let's define the Python Interface. I want a list of Python Classes and Methods that
 would allow a developer to do [X, Y, and Z] without knowing the Go implementation. Do not write the implementation logic; just write the
 Class signatures and Docstrings in Python."
 - Goal: This creates the "Skeleton" you mentioned. By focusing on signatures and docstrings, you aren't wasting tokens on implementation
 details.

 #### Stage 3: The "Incremental Implementation" Phase (The Heavy Lifting)

 Now, you implement the skeleton piece by piece. This is where most people fail by trying to do it all at once.
 - Prompt: "Now, let's implement the Client class from our skeleton. To do this accurately, please read internal/transport/client.go and
 pkg/models/user.go in the Go repo. Ensure the Python Client handles the authentication flow exactly as the Go version does. Use asyncio
 for the Python implementation."
 - Goal: You are providing the "source of truth" (the specific Go files) only when the model is ready to write the specific Python code.

 ### Why this works for Gemma-4 specifically:

 1. Context Management: By breaking it into stages, you clear the "noise" of the Go implementation once the "Map" is built. You aren't
 carrying 50 Go files in the context while trying to write 10 Python files.
 2. Precision: You are directing the "Attention" of the model. Instead of "Look at everything," you are saying "Look at these 2 files to
 solve this 1 specific class."
 3. Verification: In Stage 1 and 2, you can check the model's work. If the "Logic Map" is wrong, you catch it before it writes a single
 line of broken Python.

 If you want to start right now, give me this command:

 │ "I need to build a Python SDK for a Go application. Let's start with Stage 1. Explore the current directory, identify the core Go
 │ modules, and give me a summary of how the application's main logic flows. Don't write any Python yet; just build the map."
