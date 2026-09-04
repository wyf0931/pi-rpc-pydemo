from pathlib import Path


def test_docker_image_includes_standard_http_and_json_cli_tools():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "FROM node:24.20.0-bookworm-slim" in dockerfile
    assert "@earendil-works/pi-coding-agent@0.84.4" in dockerfile
    assert "curl" in dockerfile
    assert "jq" in dockerfile
    assert "curl_cffi" not in dockerfile
