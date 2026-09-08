from pathlib import Path


def test_production_deploy_validates_both_pi_host_mounts():
    script = Path("bin/deploy-server.sh").read_text(encoding="utf-8")

    assert "for path_var in PI_HOST_HOME PI_HOST_AGENTS_HOME; do" in script
    assert 'path_value="${!path_var:-}"' in script
    assert '"$path_var is required in $ROOT/.env.ops"' in script
    assert (
        '"$path_var must be an existing absolute host directory: $path_value"' in script
    )
    assert '[[ "$path_value" != /* || ! -d "$path_value" ]]' in script


def test_production_deploy_prints_compose_diagnostics_on_startup_failure():
    script = Path("bin/deploy-server.sh").read_text(encoding="utf-8")

    assert 'echo "container startup FAILED; collecting diagnostics" >&2' in script
    assert 'docker compose "${COMPOSE_FILES[@]}" ps >&2 || true' in script
    assert (
        'docker compose "${COMPOSE_FILES[@]}" logs --tail 100 oma-studio >&2 || true'
        in script
    )
    assert "show_compose_diagnostics" in script
