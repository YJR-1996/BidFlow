"""统计报表项目联动测试：project_id 筛选、风险概览/合规健康度按项目、越权"""


def _setup_project_with_data(client, headers, name="联动项目"):
    pid = client.post("/api/projects", json={"name": name}, headers=headers).json()["data"]["id"]
    # 需求 + 合规 issue
    client.post(
        f"/api/projects/{pid}/tender-documents",
        files={"file": ("t.txt", "资格要求：必须提供营业执照。\n技术要求：支持高并发。".encode(), "text/plain")},
        headers=headers,
    )
    return pid


class TestStatsProjectLink:
    def test_stats_requires_auth(self, client):
        r = client.get("/api/stats")
        assert r.status_code in (401, 403)

    def test_stats_all_projects_default(self, client, auth_headers):
        """project_id 不传 → 全部项目汇总，结构完整"""
        r = client.get("/api/stats", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["scope"]["project_id"] is None
        assert "risk_overview" in data
        assert "compliance" in data
        assert "trend_chart" in data

    def test_stats_project_scoped(self, client, auth_headers):
        """project_id 有值 → risk_overview 按该项目，scope 带项目名"""
        pid = _setup_project_with_data(client, auth_headers)
        r = client.get(f"/api/stats?project_id={pid}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["scope"]["project_id"] == pid
        assert data["scope"]["project_name"] == "联动项目"
        # 单项目视图：项目总数 = 1
        assert data["core_metrics"]["total_projects"] == 1

    def test_stats_other_user_project_denied(self, client, auth_headers):
        """他人项目 → 404（越权拦截）"""
        pid = _setup_project_with_data(client, auth_headers)
        client.post("/api/auth/register", json={"username": "stats_b", "password": "pass123456"})
        resp = client.post("/api/auth/login", json={"username": "stats_b", "password": "pass123456"})
        other = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        r = client.get(f"/api/stats?project_id={pid}", headers=other)
        assert r.status_code in (403, 404)

    def test_stats_time_range_param(self, client, auth_headers):
        """time_range 参数（7d/30d/90d）生效：trend_chart 桶数匹配"""
        for period, expected in [("7d", 7), ("30d", 30)]:
            r = client.get(f"/api/stats?period={period}", headers=auth_headers)
            assert r.status_code == 200
            data = r.json()["data"]
            assert len(data["trend_chart"]) == expected
