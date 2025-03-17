> [!NOTE]
> These are very thoughts on TRP in interactive computing. I hope to develop
> them into a paper or blog post later.

Transparent reactive programming (TRP) is a paradigm that can be applied across
many programming languages. At its core, it simplifies programming against
values that change over time. For example, in traditional imperative
programming, `x = 1; y = x + 1` means that `y` is calculated once and won’t
change if `x` is updated.

In contrast, a classic example of TRP is spreadsheets, where as cell defines a
_relationship_ between values, such as `y := x + 1`. In this case, the system
does not take a snapshot of `x` and `y` at the time of the formula definition,
but rather marks `y` as dependent on `x`. When `x` changes, the system
automatically updates `y`. These time-varying values are known as _signals_.
Whenever a signal changes, the system automatically updates all dependents.

In a world without reactive programming, the dominant model is callback-based or
event-driven programming. It’s easy to understand how to do callback-based
programming, but it’s really hard to do it right—especially as the number of
events, callbacks, and intermediates grows, making the state more complex.
Ensuring both performance and correctness becomes a challenge, and it’s easy to
miss updating some aspect of your calculation, leading to incorrect results.

Spreadsheets are a classic success story of TRP in action, which raises the
question: why hasn't TRP been more widely adopted beyond spreadsheets,
especially in other interactive computing environments like Jupyter notebooks?

I strongly believe that TRP is a natural fit for interactive computing; it just
has not yet found the right interface within popular tools to become mainstream.

The reason for this limited adoption is not entirely clear, but my hypothesis is
that it's largely cultural and shaped by the strong influence of Jupyter in the
data science community. Data scientists typically learn a batch-oriented
programming style, where data is loaded, transformed, and analyzed in a linear
sequence. This style of programming doesn’t benefit much from TRP concepts, as
scripts are generally executed once to produce a final result. In contrast,
application programming inherently requires managing state, and TRP has gained
traction for its ability to model complex stateful systems with relatively
simple, declarative code.

Exploratory and interactive analysis in computational notebooks is often
non-linear, despite the linear style of programming. Since Jupyter code cells
lack the reactivity semantics of spreadsheet cells, data scientists must
manually re-execute cells whenever values change. This human-driven event loop
is error-prone and can suffer from the same, if not worse, issues as
event-driven programming: it’s easy to miss a dependent computation, leading to
incorrect results.

This process is akin to managing callbacks in event-driven programming, where
understanding the execution flow and ensuring correctness requires keeping a lot
of information in mind. The resulting complexity often obscures data
synchronization bugs, making it difficult to assess the impact of a single
change on the entire notebook. This limitation has led to common criticisms of
computational notebooks, often misattributing the problem to interactive
computing itself, when the real issue is the lack of reactivity.

The signals library introduces TRP to Python, with a focus on integrating with
Jupyter. By gradually adding signals to your notebooks, you can incrementally
learn reactive programming. Notebook cells automatically respond to updates like
spreadsheets, simplifying complex workflows.

Unlike new notebook runtimes or kernels, signals is "just a library" that fits
naturally within Jupyter without requiring special extensions. This makes it
easy to adopt and experiment with in your existing code. Additionally, by making
notebooks reactive, signals offers a pathway to transition notebook code into
applications, such as dashboards, without a complete paradigm shift.
