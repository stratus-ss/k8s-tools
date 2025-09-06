#!/usr/bin/env python3
"""
Shared pytest configuration and fixtures for all tests.
"""

import pytest
import sys
import os

# Add the parent directory to Python path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment automatically for all tests"""
    # Ensure modules can be imported from parent directory
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
