# signals

primitives for transparent reactive programming in python

## install

```python
pip install signals
```

## usage

```python
from signals import Signal, computed, effect

a = Signal(0)
b = Signal(2)
c = computed(lambda: a() + b())

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

TRP is exceptionally well-suited for interactive computing. Its mathematical
foundations are simple and familiar, yet its application within interactive
data analysis environments has been limited to spreadsheets.

`signals` serves two main purposes:

- A standalone TRP implementation for Python
- An integration of TRP into Jupyter-like environments

The main goal of `signals` is to provide stable and robust impelemtnation of
TRP for Python, and to explore its use in data science workflows. Adopting
these primitives at the analysis level offers several potential benefits:

1.) It helps manage non-linearity other issues in complex/stateful notebooks.

2.) It gradually introduces reactive programming concepts to data science
    workflows without requiring a total paradigm shift.

3.) It lays a foundation for transitioning from notebooks to more interactive
    applications (e.g., dashboards) without introducing a completely new
    programming model.

## development

this project uses [`rye`](https://rye-up.com/) for development.

```sh
rye lint # lints code
rye fmt  # formats code
rye test # runs tests
```
