"""chat 路由测试：权限校验 + 对话（mock LLM 工具调用）"""
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


def _setup_project(client, headers):
    pid = client.post("/api/projects", json={"name": "对话测试项目"}, headers=headers).json()["data"]["id"]
    return pid


class TestChatRoute:
    def test_chat_requires_auth(self, client):
        r = client.post("/api/projects/1/chat", json={"message": "你好"})
        assert r.status_code in (401, 403)

    def test_chat_other_user_denied(self, client, auth_headers):
        pid = _setup_project(client, auth_headers)
        # 注册另一个用户
        client.post("/api/auth/register", json={"username": "chat_user_b", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "chat_user_b", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.post(f"/api/projects/{pid}/chat", json={"message": "你好"}, headers=other)
        assert r.status_code in (403, 404)

    def test_chat_empty_message_400(self, client, auth_headers):
        pid = _setup_project(client, auth_headers)
        r = client.post(f"/api/projects/{pid}/chat", json={"message": "   "}, headers=auth_headers)
        assert r.status_code in (400, 404)

    def test_chat_returns_reply(self, client, auth_headers):
        """mock chat_service.chat，验证路由透传（不真调 LLM）"""
        pid = _setup_project(client, auth_headers)
        from app.services import chat_service as chat_service_module

        fake_result = {"reply": "项目共 5 条需求，其中 2 条未匹配。", "tool_calls_used": ["query_match"], "degraded": False}
        with patch.object(chat_service_module.chat_service, "chat", return_value=fake_result) as mock_chat:
            r = client.post(f"/api/projects/{pid}/chat", json={"message": "匹配情况如何？"}, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["reply"] == fake_result["reply"]
        assert data["tool_calls_used"] == ["query_match"]
        # chat_service 应收到 project_id + owner_id + 消息
        args = mock_chat.call_args
        assert args.kwargs["project_id"] == pid
        assert args.kwargs["user_message"] == "匹配情况如何？"
