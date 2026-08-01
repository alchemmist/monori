from app.mutation_gate_demo import mutation_gate_demo


def test_mutation_gate_demo_handles_positive_values() -> None:
    assert mutation_gate_demo(1) == 2
