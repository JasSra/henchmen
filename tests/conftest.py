"""Test configuration and fixtures"""
import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.db"
    yield str(db_path)
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_config():
    """Test configuration"""
    return {
        "database_path": ":memory:",
        "github_webhook_secret": "test-secret-123"
    }
