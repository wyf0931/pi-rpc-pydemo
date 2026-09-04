from pathlib import Path


def test_docker_image_includes_standard_http_and_json_cli_tools():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "curl" in dockerfile
    assert "jq" in dockerfile
    assert "curl_cffi" not in dockerfile
