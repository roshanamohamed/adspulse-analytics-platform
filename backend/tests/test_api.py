import importlib
from fastapi.testclient import TestClient

def test_api_and_idempotent_sync(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'test.sqlite'))
    from app import main
    importlib.reload(main)
    with TestClient(main.app) as client:
        assert client.get('/api/health').status_code == 200
        before=client.get('/api/campaigns').json()
        assert len(before)==7
        assert client.get('/api/summary').json()['campaigns']==7
        assert len(client.get('/api/trends').json())==30
        response=client.post('/api/sync',json={'source':'All'})
        assert response.status_code==200
        assert len(client.get('/api/campaigns').json())==7
        assert before==client.get('/api/campaigns').json()
        assert len(client.get('/api/campaigns?channel=Search').json())==3
        assert len(client.get('/api/campaigns?search=brand').json())==1
        failed=client.post('/api/sync',json={'source':'Search Partner','simulate_failure':True}).json()
        assert failed['status']=='partial_failure'
        assert failed['runs'][0]['attempts']==3
        assert client.get('/api/activity').json()['runs'][0]['status']=='failed'
