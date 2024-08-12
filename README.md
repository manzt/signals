# signals

primitives for transparent reactive programming in python

## install

```python
pip install signals
```

## usage

```python
from signals import Signal, effect

a = Signal(0)
b = Signal(2)
def c():
    return a() + b()

print(c()) # 2

a.set(1)
print(c()) # 3

b.set(3)
print(c()) # 4

# Log the values of a, b, c whenever one changes
@effect
def log_abc():
    print(a(), b(), c())

a.set(2) # prints (2, 3, 5)
```

## cell magic

we also provide a ipython cell magic `%%effect`, which offers a convenient way
re-execute cells that use signals.

`In[1]:`

```python
%load_ext signals
from signals import Signal

a = Signal(0)
b = Signal(2)
```

`In[2]:`

```python
%%effect
a() + b() # re-evaluates the cell whenever a or b changes
```

`In[3]:`

```python
a.set(1)
```

## what

`signals` is an implementation of transparent reactive programming (TRP) for Python.

TRP is a declarative programming paradigm for expressing _relationships_ between
values that vary over time. These time-varying values are known as _signals_.
Whenever a signal changes, the system automatically updates all dependents.

Spreadsheets are the classic example of TRP: cells linked by formulas update
automatically when values change. The system discovers dependencies by
observing data access, dynamically constructing a dependency graph.

The key features of TRP include:

- **declarative**: the programmer specifies relationships between values
- **transparent**: the system (not the programmer) automatically tracks dependencies
- **efficient**: the system performs only the necessary computations to ensure relationships hold over time

## why

> [!NOTE]
> These are very thoughts on TRP in interactive computing. I hope to develop
> them into a paper or blog post later.

TRP has proven effective in structuring programs that respond to events and
update values over time, particularly in application programming. At its core,
TRP is a paradigm for programming against values that change over time—a
concept that extends beyond user interfaces to many other domains. Spreadsheets
are a classic success story of TRP in action, which raises the question: why
hasn't TRP been more widely adopted beyond spreadsheets, especially in other
interactive computing environments like Jupyter notebooks?

I strongly believe that TRP is a natural fit for interactive computing; it just
has not yet found the right interface within popular tools to become mainstream.

The reason for this limited adoption is not entirely clear, but my hypothesis
is that it's largely cultural, and shaped by the strong influence of Jupyter in
the data science community.

Data scientists typically learn a batch-oriented programming style, where data
is loaded, transformed, and analyzed in a linear sequence. This style of
programming doesn’t benefit much from TRP concepts, as scripts are generally
executed once to produce a final result. In contrast, application programming
inherently requires managing state, and TRP has gained traction for its ability
to model complex stateful systems with relatively simple, declarative code.

Exploratory and interactive analysis in computational notebooks is often
non-linear, even though much of linear style of programming. Since Jupyter code
cells lack the reactivity semantics of spreadsheet cells, data scientists must
manually re-execute cells whenever values change. This human-driven event loop
is error-prone and can suffer from the same, if not worse, issues as
event-driven programming: it’s easy to miss a dependent computation, leading to
incorrect results.

This process is akin to managing callbacks in event-driven programming, where
understanding the execution flow and ensuring correctness requires keeping a
lot of information in mind. The resulting complexity often obscures data
synchronization bugs, making it difficult to assess the impact of a single
change on the entire notebook. This limitation has led to common criticisms of
computational notebooks, often misattributing the problem to interactive
computing itself, when the real issue is the lack of reactivity.

The `signals` library introduces TRP to Python, with a focus on integrating
with Jupyter. By gradually adding _signals_ to your notebooks, you can
incrementally learn reactive programming. Notebook cells automatically respond
to updates like spreadsheets, simplifying complex workflows.

Unlike new notebook runtimes or kernels, `signals` is "just a library" that
fits naturally within Jupyter without requiring special extensions. This makes
it easy to adopt and experiment with in your existing code. Additionally, by
making notebooks reactive, `signals` offers a pathway to transition notebook code
into applications, such as dashboards, without a complete paradigm shift.

## development

this project uses [`rye`](https://rye-up.com/) for development.

```sh
rye lint # lints code
rye fmt  # formats code
rye test # runs tests
```
