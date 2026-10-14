import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from werkzeug.security import generate_password_hash
from acepressure.app import create_app
@pytest.fixture
def app(tmp_path):
    return create_app(dict(TESTING=True,DATA_DIR=str(tmp_path),SECRET_KEY='s'*48,BRIDGE_TOKEN='b'*48,OVERLAY_TOKEN='o'*48,ADMIN_PASSWORD_HASH=generate_password_hash('test-password-123'),DEMO_MODE=True,ENV_FILE=str(tmp_path/'none.env')))
@pytest.fixture
def client(app):return app.test_client()
@pytest.fixture
def admin(client):
    r=client.post('/api/login',json={'password':'test-password-123'});return client,{'X-CSRF-Token':r.json['csrf']}
