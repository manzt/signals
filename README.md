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

`signals` is an implementation of transparent reactive programming (TRP) for
Python.

TRP is a declarative programming paradigm for expressing _relationships_ between
values that vary over time. These time-varying values are known as _signals_.
Whenever a signal changes, the system automatically updates all dependents.

Spreadsheets are the classic example of TRP: cells linked by formulas update
automatically when values change. The system discovers dependencies by observing
data access, dynamically constructing a dependency graph.

The key features of TRP include:

- **declarative**: the programmer specifies relationships between values
- **transparent**: the system (not the programmer) automatically tracks
  dependencies
- **efficient**: the system performs only the necessary computations to ensure
  relationships hold over time

## why

TL;DR - TRP is a natural fit for interactive computing but has so far lacked the
right interface in popular tools to go mainstream. You can read more of my
[unfinished thoughts](./notes.md) on this topic.

## development

this project uses [`uv`](https://github.com/astral-sh/uv) for development.

```sh
uv run ruff check  # lints code
uv run ruff format # formats code
uv run pytest      # run tests
```
