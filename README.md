# signals

A signals implementation for Python

## install

```python
pip install signals
```

## usage

```python
from signals import Signal, computed, effect

a = Signal(0)
b = Signal(2)
c = computed(lambda: a.value + b.value)

print(c.value) # 2

a.value = 1
print(c.value) # 3

b.value = 3
print(c.value) # 4

# Log the values of a, b, c whenever one changes
@effect
def log_abc():
    print(a.value, b.value, c.value)

a.value = 2 # prints (2, 3, 5)
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
a.value + b.value # re-evaluates the cell whenever a or b changes
```

`In[3]:`

```python
a.value = 1
```


## what

Signals are a declarative programming model for updating based on fine-grained
changes. With signals, application state is represented as a directed graph of
relationships between other signals. However, the most important part of
signals is that you don't need to manage the graph yourself.

Instead, you declare signals and their relationships, and the signal system
automatically tracks dependencies and executes necessary computations when
values change. Singal-like constructs have been adopted by popular UI libraries
and non-UI contexts (e.g., build systems to avoid uneccessary rebuilds).

## why

Signals are an easier way to manage state. We need something in Python other
than callbacks and events. This repo is a playground to explore patterns for
using a signal-based system in Python.

## ideas

Signals for widgets

```py
@anywidget.dataclass
class Counter:
    count: int

a = Counter(count=0) # creates a signal internally

shared_count = Signal(0)
b = Counter(count=shared_count) # creates a signal internally
c = Counter(count=shared_count) # creates a signal internally

# behind the scenes, creating Counter creates an effect to update the frontend view
# when the count changes. E.g.,
# @effect
# def update():
#     self.comm.send('update', self.count)
#
# Updates b/c views because they share a signal, and have separate effects
shared_count.value += 1
```

## development

this project uses [`rye`](https://rye-up.com/) for development.

```sh
rye lint # lints code
rye fmt  # formats code
rye test # runs tests
```
