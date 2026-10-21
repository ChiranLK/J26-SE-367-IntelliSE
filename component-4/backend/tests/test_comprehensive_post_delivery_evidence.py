from app.services.code_analysis import inspect_python_project
from app.services.post_delivery_xai_service import PostDeliveryXaiService


def test_multi_file_project_evidence_is_bounded_and_preserves_real_symbols():
    files = {
        "shop/pricing.py": (
            "def final_price(subtotal: float, discount: float) -> float:\n"
            "    if subtotal < 0:\n"
            "        raise ValueError('subtotal')\n"
            "    return subtotal * (1 - discount)\n"
        ),
        "shop/checkout.py": (
            "from shop.pricing import final_price\n\n"
            "def checkout(subtotal: float) -> float:\n"
            "    return final_price(subtotal, 0.1)\n"
        ),
        "tests/test_unit.py": "def test_placeholder():\n    assert True\n",
        "notes.txt": "not Python source",
    }

    evidence = inspect_python_project(
        files,
        entrypoint="shop/pricing.py",
        max_source_files=2,
        max_source_chars=140,
    )

    assert evidence["analyzed_source_files"][0] == "shop/pricing.py"
    assert set(evidence["analyzed_source_files"]) == {"shop/pricing.py", "shop/checkout.py"}
    assert evidence["test_files"] == ["tests/test_unit.py"]
    assert evidence["source_excerpt_char_count"] <= 140
    symbols = {
        function["name"]
        for module in evidence["modules"]
        for function in module["functions"]
    }
    assert symbols == {"final_price", "checkout"}
    final_price = next(
        function
        for module in evidence["modules"]
        for function in module["functions"]
        if function["name"] == "final_price"
    )
    assert final_price["validation_conditions"] == ["subtotal < 0"]
    assert final_price["raised_exceptions"] == ["ValueError('subtotal')"]
    assert final_price["return_expressions"] == ["subtotal * (1 - discount)"]


def test_llm_grounding_rejects_unknown_files_and_positive_web_claims():
    evidence = {"analyzed_source_files": ["shop/pricing.py"]}
    ast = {"imports": [], "functions": []}
    llm = {
        "software_overview": "Pricing is defined in [source: pricing.py].",
        "architecture_explanation": "The system exposes a REST API from server.py.",
        "api_and_data_flow": "No HTTP API is evidenced by the analyzed source.",
    }

    validated, warnings = PostDeliveryXaiService()._validate_llm_grounding(llm, evidence, ast)

    assert "software_overview" in validated
    assert "api_and_data_flow" in validated
    assert "architecture_explanation" not in validated
    assert any("unknown source" in warning or "unsupported web" in warning for warning in warnings)

