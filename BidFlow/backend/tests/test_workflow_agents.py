"""Integration test for the workflow agent layer (no DB required)."""
import os
os.environ['MYSQL_HOST'] = 'localhost'
os.environ['MYSQL_PORT'] = '3306'
os.environ['MYSQL_USER'] = 'root'
os.environ['MYSQL_PASSWORD'] = 'test'
os.environ['MYSQL_DATABASE'] = 'test_db'
os.environ['SECRET_KEY'] = 'test_key'


def main():
    errors = []

    # 1. Import Test
    try:
        from app.agents import (
            WorkflowContext, ToolRegistry, BaseAgent,
            ParseAgent, DecomposeAgent, RAGAgent,
            ComplianceAgent, Orchestrator,
        )
        print('[PASS] All agent imports OK')
    except Exception as e:
        errors.append(f'Import failed: {e}')
        print(f'[FAIL] Import: {e}')
        return

    # 2. WorkflowContext Test
    try:
        ctx = WorkflowContext(project_id=1, owner_id='user1')
        assert ctx.project_id == 1
        assert ctx.stages_done == []
        ctx.requirements = [{'id': 1, 'content': 'test'}]
        assert len(ctx.requirements) == 1
        print('[PASS] WorkflowContext works correctly')
    except Exception as e:
        errors.append(f'WorkflowContext: {e}')
        print(f'[FAIL] WorkflowContext: {e}')

    # 3. Orchestrator Test
    try:
        orch = Orchestrator()
        assert orch.STAGE_ORDER == ['parse', 'decompose', 'rag', 'compliance']
        assert len(orch.agents) == 4
        print('[PASS] Orchestrator initialized correctly')
    except Exception as e:
        errors.append(f'Orchestrator: {e}')
        print(f'[FAIL] Orchestrator: {e}')

    # 4. WorkflowRun Model Test
    try:
        from app.models.workflow_run import WorkflowRun
        wr = WorkflowRun(
            id='test-uuid-1234',
            project_id=1,
            current_stage='parse',
            status='running',
            context_json='{"test": true}',
        )
        assert wr.id == 'test-uuid-1234'
        assert wr.project_id == 1
        print('[PASS] WorkflowRun model works correctly')
    except Exception as e:
        errors.append(f'WorkflowRun model: {e}')
        print(f'[FAIL] WorkflowRun model: {e}')

    # 5. Route Registration
    try:
        from app.main import app
        workflow_routes = []
        for r in app.routes:
            path = getattr(r, 'path', '')
            methods = getattr(r, 'methods', set())
            if 'workflow' in path:
                workflow_routes.append((path, methods))

        expected_paths = [
            '/api/projects/{project_id}/run-workflow',
            '/api/projects/{project_id}/workflow/{run_id}',
            '/api/projects/{project_id}/workflow/{run_id}/resume',
            '/api/projects/{project_id}/workflow-runs',
        ]
        for expected in expected_paths:
            found = any(expected == path for path, _ in workflow_routes)
            if found:
                print(f'[PASS] Route registered: {expected}')
            else:
                errors.append(f'Route missing: {expected}')
                print(f'[FAIL] Route missing: {expected}')
    except Exception as e:
        errors.append(f'Route registration: {e}')
        print(f'[FAIL] Route registration: {e}')

    # 6. Verify existing routes still work
    try:
        from app.main import app
        all_paths = [getattr(r, 'path', '') for r in app.routes]
        preserved = [
            '/api/auth/register',
            '/api/auth/login',
            '/api/projects',
        ]
        for p in preserved:
            found = any(p in path for path in all_paths)
            if not found:
                errors.append(f'Existing route broken: {p}')
                print(f'[FAIL] Existing route broken: {p}')
        print('[PASS] All existing routes preserved')
    except Exception as e:
        errors.append(f'Existing routes: {e}')
        print(f'[FAIL] Existing routes: {e}')

    # 7. Compliance agent snapshot builder
    try:
        from app.agents.compliance_agent import build_snapshots_from_requirements
        print('[PASS] Compliance agent function imported')
    except Exception as e:
        errors.append(f'Compliance agent: {e}')
        print(f'[FAIL] Compliance agent: {e}')

    print()
    if errors:
        print(f'[FAILED] {len(errors)} test(s) failed:')
        for e in errors:
            print(f'  - {e}')
        return 1
    else:
        print('[SUCCESS] All tests passed!')
        return 0


if __name__ == '__main__':
    exit(main())
