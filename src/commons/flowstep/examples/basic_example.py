"""Basic usage example of the FlowStep pipeline."""

from ..builder import FlowBuilder
from ..core import FlowContext, Step


class LoadDataStep(Step):
    """Step to load initial data."""

    def execute(self, context: FlowContext) -> None:
        data = {
            "users": [
                {"id": 1, "name": "Alice", "age": 30},
                {"id": 2, "name": "Bob", "age": 25},
                {"id": 3, "name": "Charlie", "age": 35},
            ]
        }
        context.put("raw_data", data)
        context.put("load_timestamp", "2024-01-01T00:00:00")

    def get_required_keys(self) -> set[str]:
        return set()

    def get_produced_keys(self) -> set[str]:
        return {"raw_data", "load_timestamp"}


class TransformDataStep(Step):
    """Step to transform the data."""

    def execute(self, context: FlowContext) -> None:
        raw_data = context.get("raw_data")
        users = raw_data.get("users", [])

        transformed = {
            "total_users": len(users),
            "users": [
                {
                    "user_id": u["id"],
                    "full_name": u["name"].upper(),
                    "is_adult": u["age"] >= 18,
                }
                for u in users
            ],
        }

        context.put("transformed_data", transformed)

    def get_required_keys(self) -> set[str]:
        return {"raw_data"}

    def get_produced_keys(self) -> set[str]:
        return {"transformed_data"}


def main():
    """Pipeline execution example."""
    print("=" * 60)
    print("FlowStep — Basic Example")
    print("=" * 60)

    flow = (
        FlowBuilder("user_processing_pipeline")
        .add_step(LoadDataStep("load"))
        .add_step(TransformDataStep("transform"))
        .build()
    )

    print(f"\n✓ Flow created: {flow}")
    print(f"  Steps: {len(flow.get_steps())}")

    print("\n--- Flow Execution ---")
    try:
        result = flow.run({"input": "test"})

        print("\n✓ Flow executed successfully!")
        print(f"\nKeys in context: {result.keys()}")
        print("\nTransformed data:")
        print(f"  {result.get('transformed_data')}")

    except Exception as e:
        print(f"\n❌ Error during execution: {e}")


if __name__ == "__main__":
    main()
