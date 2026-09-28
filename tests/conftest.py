import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Route all DB/upload artifacts from tests into a throwaway temp dir.
_tmp = tempfile.mkdtemp(prefix="nlq_test_")
os.environ["DB_DIR"] = os.path.join(_tmp, "db")
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")


@pytest.fixture()
def sample_csv_path(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text(
        "order_id,item,qty,price,order_date,country\n"
        "1,Widget,2,9.99,2024-01-01,US\n"
        "1,Gadget,1,19.99,2024-01-01,US\n"
        "2,Widget,5,9.99,2024-01-02,UK\n"
        "3,Gizmo,1,49.99,2024-02-01,UK\n"
        "3,Widget,3,9.99,2024-02-01,UK\n"
    )
    return str(p)
