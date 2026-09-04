import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def pytest_configure(config):
    config.addinivalue_line("markers", "req(*ids): requirement ids verified by this test")
