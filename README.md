# signals

A signals implementation for Python

```python
pip install signals # TODO: new name
```

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

@effect
def print_c():
    print(c.value)

a.value = 2 # prints 5
```
