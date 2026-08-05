# -*- coding: utf-8 -*-
"""资料改归属测试：端点鉴权/越权 + 向量归属同步后检索隔离"""


def _upload_material(client, headers, filename="qualification-test.txt", scope="company", project_id=None):
    """上传资料（txt 避免 PDF 解析依赖），返回 (doc_id, project_id)"""
    pid = None
    if project_id is None and scope == "project":
        pid = client.post("/api/projects", json={"name": "归属测试项目"}, headers=headers).json()["data"]["id"]
        project_id = pid
    form = {"scope": scope}
    if project_id:
        form["project_id"] = str(project_id)
    r = client.post(
        "/api/company-documents",
        data=form,
        files={"file": (filename, "资质内容：营业执照、质量管理体系认证。".encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"], project_id


class TestMaterialScope:
    def test_change_company_to_project(self, client, auth_headers):
        """公司级 → 项目级：列表返回 project_name，向量归属同步"""
        doc_id, _ = _upload_material(client, auth_headers, scope="company")
        pid = client.post("/api/projects", json={"name": "目标项目"}, headers=auth_headers).json()["data"]["id"]

        r = client.patch(
            f"/api/company-documents/{doc_id}/scope",
            data={"scope": "project", "project_id": str(pid)},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["scope"] == "project"
        assert r.json()["project_id"] == pid

        # 列表显示归属项目名
        docs = client.get("/api/company-documents", headers=auth_headers).json()
        target = [d for d in docs if d["id"] == doc_id][0]
        assert target["scope"] == "project"
        assert target["project_name"] == "目标项目"

        # 向量归属同步：检索隔离生效（目标项目可搜到，其他项目搜不到）
        from app.services.vector_store import vector_store_service
        assert any(
            v.get("metadata", {}).get("doc_id") == doc_id and v.get("project_id") == pid
            for v in vector_store_service._vectors
        )
        assert all(
            v.get("metadata", {}).get("scope") == "project"
            for v in vector_store_service._vectors
            if v.get("metadata", {}).get("doc_id") == doc_id
        )

    def test_change_project_to_company(self, client, auth_headers):
        """项目级 → 公司级：project_id 清空，向量 scope 变 company"""
        doc_id, pid = _upload_material(client, auth_headers, scope="project")
        r = client.patch(
            f"/api/company-documents/{doc_id}/scope",
            data={"scope": "company"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["project_id"] is None

        from app.services.vector_store import vector_store_service
        assert all(
            v.get("metadata", {}).get("scope") == "company"
            for v in vector_store_service._vectors
            if v.get("metadata", {}).get("doc_id") == doc_id
        )
        assert all(
            v.get("project_id") is None
            for v in vector_store_service._vectors
            if v.get("metadata", {}).get("doc_id") == doc_id
        )

    def test_project_scope_requires_project(self, client, auth_headers):
        """项目级必填 project_id"""
        doc_id, _ = _upload_material(client, auth_headers, scope="company")
        r = client.patch(
            f"/api/company-documents/{doc_id}/scope",
            data={"scope": "project"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_other_user_denied(self, client, auth_headers):
        """越权：他人资料 404"""
        doc_id, _ = _upload_material(client, auth_headers, scope="company")
        client.post("/api/auth/register", json={"username": "scope_b", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "scope_b", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.patch(
            f"/api/company-documents/{doc_id}/scope",
            data={"scope": "project", "project_id": "1"},
            headers=other,
        )
        assert r.status_code == 404

    def test_target_project_must_be_owned(self, client, auth_headers):
        """目标项目必须归属当前用户"""
        doc_id, _ = _upload_material(client, auth_headers, scope="company")
        client.post("/api/auth/register", json={"username": "scope_c", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "scope_c", "password": "pass123456"})
        other_pid = client.post("/api/projects", json={"name": "他人项目"}, headers={
            "Authorization": f"Bearer {resp.json()['access_token']}"
        }).json()["data"]["id"]
        r = client.patch(
            f"/api/company-documents/{doc_id}/scope",
            data={"scope": "project", "project_id": str(other_pid)},
            headers=auth_headers,
        )
        assert r.status_code == 404
