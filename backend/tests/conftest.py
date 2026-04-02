"""
conftest.py — pytest configuration và shared fixtures.

Set NEXUS_DATA_DIR trước khi import bất kỳ module nào để tránh
PermissionError khi CI cố tạo /app/data (chỉ tồn tại trong Docker).
"""

import os
import tempfile

# Phải set TRƯỚC khi src.main được import — module-level singletons
# (ABRouter, EvalDataset) đọc env var này ngay lúc khởi tạo.
# CI workflow set NEXUS_DATA_DIR=/tmp/nexus-test-data nên setdefault không override.
_tmp_data = tempfile.mkdtemp(prefix="nexus_test_")
os.environ.setdefault("NEXUS_DATA_DIR", _tmp_data)
