# FlowStep — Data Processing Pipeline Framework

FlowStep is a lightweight, flexible framework for building and executing data processing pipelines in Python. It provides a clean, fluent API for constructing sequential data processing workflows.

## Quick Start

```python
from commons.flowstep import Flow, Step, FlowContext, FlowBuilder

# Define your custom steps
class LoadDataStep(Step):
    def execute(self, context: FlowContext) -> None:
        data = {"users": [{"id": 1, "name": "Alice"}]}
        context.put("raw_data", data)

    def get_required_keys(self) -> set[str]:
        return set()

    def get_produced_keys(self) -> set[str]:
        return {"raw_data"}


class ProcessDataStep(Step):
    def execute(self, context: FlowContext) -> None:
        raw_data = context.get("raw_data")
        processed = [user["name"].upper() for user in raw_data["users"]]
        context.put("processed_data", processed)

    def get_required_keys(self) -> set[str]:
        return {"raw_data"}

    def get_produced_keys(self) -> set[str]:
        return {"processed_data"}


# Build and run the pipeline
flow = (FlowBuilder("data_pipeline")
    .add_step(LoadDataStep("load"))
    .add_step(ProcessDataStep("process"))
    .build())

result = flow.run()
print(result.get("processed_data"))  # ['ALICE']
```

## Core Concepts

### FlowBuilder

The builder class provides a fluent API for constructing pipelines:

```python
flow = (FlowBuilder("my_pipeline")
    .add_step(step1)
    .add_step(step2)
    .add_step(step3)
    .build())
```

### Step

Abstract base class for all pipeline steps. Each step must implement:

- `execute(context)`: The main logic of the step
- `get_required_keys()`: Keys that must exist in the context before execution
- `get_produced_keys()`: Keys that will be added to the context after execution

```python
class MyStep(Step):
    def execute(self, context: FlowContext) -> None:
        # Your logic here
        pass

    def get_required_keys(self) -> set[str]:
        return {"input_key"}

    def get_produced_keys(self) -> set[str]:
        return {"output_key"}
```

### FlowContext

A container for sharing data between pipeline steps:

```python
context = FlowContext({"initial": "data"})

context.put("key", "value")
value = context.get("key")

if context.has("key"):
    ...

all_keys = context.keys()
data_dict = context.to_dict()
```

### Flow

The pipeline orchestrator that executes steps sequentially:

```python
flow = Flow("my_pipeline", [step1, step2, step3])
result = flow.run({"initial": "data"})
```

## API Reference

### FlowBuilder

#### `__init__(pipeline_name: str)`

Initialize the builder with a pipeline name.

#### `add_step(step: Step) -> Self`

Add a step to the pipeline. Returns self for method chaining.

#### `build(validate: bool = False, initial_context: FlowContext | dict | None = None) -> Flow`

Build and return the configured pipeline. Pass `validate=True` to run structural validation before returning — raises `FlowValidationError` on any ERROR-level finding.

---

### Step

#### `__init__(name: str)`

Initialize the step with a unique name.

#### `execute(context: FlowContext) -> None` (abstract)

Execute the step logic. Must be implemented by subclasses.

#### `get_required_keys() -> set[str]` (abstract)

Return the set of keys required from the context.

#### `get_produced_keys() -> set[str]` (abstract)

Return the set of keys that will be produced in the context.

#### `name: str` (property)

Get the step name.

---

### FlowContext

#### `__init__(initial_data: dict[str, Any] | None = None)`

Initialize the context with optional initial data.

#### `put(key: str, value: Any) -> None`

Set a value in the context.

#### `get(key: str) -> Any`

Retrieve a value from the context. Raises `KeyError` if the key does not exist.

#### `has(key: str) -> bool`

Check if a key exists in the context.

#### `keys() -> set[str]`

Return all keys present in the context.

#### `to_dict() -> dict[str, Any]`

Return a copy of the internal dictionary.

---

### Flow

#### `__init__(name: str, steps: list[Step])`

Initialize the pipeline with a name and list of steps.

#### `run(initial_context: FlowContext | dict | None = None) -> FlowContext`

Execute the pipeline and return the final context.

#### `get_steps() -> list[Step]`

Return a copy of the steps list.

#### `name: str` (attribute)

The pipeline name.

---

### FlowExecutionError

Raised when a step fails during execution.

#### Attributes

- `step_name: str` — Name of the step that failed
- `original_error: Exception` — The original exception that was raised

## Examples

### Example 1: Data Transformation Pipeline

```python
from commons.flowstep import FlowBuilder, Step, FlowContext

class LoadCSVStep(Step):
    def execute(self, context: FlowContext) -> None:
        data = [{"id": 1, "value": 10}, {"id": 2, "value": 20}, {"id": 3, "value": 30}]
        context.put("csv_data", data)

    def get_required_keys(self) -> set[str]:
        return set()

    def get_produced_keys(self) -> set[str]:
        return {"csv_data"}


class FilterStep(Step):
    def __init__(self, name: str, threshold: int):
        super().__init__(name)
        self.threshold = threshold

    def execute(self, context: FlowContext) -> None:
        data = context.get("csv_data")
        filtered = [row for row in data if row["value"] > self.threshold]
        context.put("filtered_data", filtered)

    def get_required_keys(self) -> set[str]:
        return {"csv_data"}

    def get_produced_keys(self) -> set[str]:
        return {"filtered_data"}


class AggregateStep(Step):
    def execute(self, context: FlowContext) -> None:
        data = context.get("filtered_data")
        context.put("total", sum(row["value"] for row in data))

    def get_required_keys(self) -> set[str]:
        return {"filtered_data"}

    def get_produced_keys(self) -> set[str]:
        return {"total"}


flow = (FlowBuilder("aggregation_pipeline")
    .add_step(LoadCSVStep("load"))
    .add_step(FilterStep("filter", threshold=15))
    .add_step(AggregateStep("aggregate"))
    .build())

result = flow.run()
print(f"Total: {result.get('total')}")  # Total: 50
```

### Example 2: Error Handling

```python
from commons.flowstep import FlowBuilder, Step, FlowContext, FlowExecutionError

class RiskyStep(Step):
    def execute(self, context: FlowContext) -> None:
        value = context.get("input")
        if value < 0:
            raise ValueError("Value cannot be negative")
        context.put("output", value * 2)

    def get_required_keys(self) -> set[str]:
        return {"input"}

    def get_produced_keys(self) -> set[str]:
        return {"output"}


flow = FlowBuilder("risky_pipeline").add_step(RiskyStep("risky")).build()

try:
    result = flow.run({"input": -5})
except FlowExecutionError as e:
    print(f"Step '{e.step_name}' failed: {e.original_error}")
    # Output: Step 'risky' failed: Value cannot be negative
```

### Example 3: Reusable Flow Factory

```python
from commons.flowstep import Flow, FlowBuilder

def create_etl_flow(name: str) -> Flow:
    return (FlowBuilder(name)
        .add_step(ExtractStep("extract"))
        .add_step(TransformStep("transform"))
        .add_step(LoadStep("load"))
        .build())

flow1 = create_etl_flow("users_etl")
flow2 = create_etl_flow("orders_etl")

result1 = flow1.run({"source": "users.csv"})
result2 = flow2.run({"source": "orders.csv"})
```

## Best Practices

### Step naming

Use descriptive, unique names:

```python
# Good
LoadDataStep("load_user_data")
ProcessDataStep("validate_emails")

# Avoid
LoadDataStep("step1")
```

### Context keys

Use clear, consistent naming:

```python
# Good
context.put("validated_users", users)

# Avoid
context.put("data", users)
```

### Error handling

Let exceptions propagate — `Flow` wraps them in `FlowExecutionError` automatically. Only catch if you need to enrich the context:

```python
class SafeStep(Step):
    def execute(self, context: FlowContext) -> None:
        data = context.get("input")
        result = self.process(data)
        context.put("output", result)
```

### Step independence

Design steps to be self-contained. Avoid side effects inside `execute` that go beyond reading/writing the context.

### Pipeline composition

Prefer small, focused steps over monolithic ones:

```python
flow = (FlowBuilder("data_pipeline")
    .add_step(LoadStep("load"))
    .add_step(ValidateStep("validate"))
    .add_step(CleanStep("clean"))
    .add_step(TransformStep("transform"))
    .add_step(SaveStep("save"))
    .build())
```
