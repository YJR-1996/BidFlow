from app.main import app


def test_core_business_routes_are_registered():
    """核心业务路由必须能从应用入口访问。"""
    paths = {route.path for route in app.routes}

    assert "/api/projects" in paths
    assert "/api/projects/{project_id}/tender-documents" in paths
    assert "/api/projects/{project_id}/requirements" in paths
    assert "/api/responses/generate" in paths
    assert "/api/compliance/projects/{project_id}/run" in paths
    assert "/api/company-documents" in paths
    assert "/api/company-documents/search" in paths
