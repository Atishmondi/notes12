def test_package_imports():
    import notes12

    assert notes12.__version__ == "0.1.0"


def test_pydantic_available():
    import pydantic

    assert pydantic.VERSION.startswith("2.")
