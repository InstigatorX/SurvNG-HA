"""Regression coverage for the integration's HTTPS security contract."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _load_api_with_aiohttp_doubles():
    """Load api.py without requiring the Home Assistant/aiohttp environments."""
    package_name = "survng_https_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / "custom_components" / "survng")]
    sys.modules[package_name] = package

    class FakeClientError(Exception):
        pass

    class FakeSSLError(FakeClientError):
        pass

    class FakeCertificateError(FakeSSLError):
        pass

    class FakeTimeout:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    aiohttp = types.ModuleType("aiohttp")
    aiohttp.ClientConnectorCertificateError = FakeCertificateError
    aiohttp.ClientConnectorSSLError = FakeSSLError
    aiohttp.ClientError = FakeClientError
    aiohttp.ClientResponse = object
    aiohttp.ClientSession = object
    aiohttp.ClientTimeout = FakeTimeout
    sys.modules["aiohttp"] = aiohttp

    for dependency in ("models", "urls"):
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{dependency}", ROOT / "custom_components" / "survng" / f"{dependency}.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

    spec = importlib.util.spec_from_file_location(
        f"{package_name}.api", ROOT / "custom_components" / "survng" / "api.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, FakeCertificateError, FakeSSLError


def test_tls_connector_errors_are_not_reported_as_generic_connection_errors() -> None:
    api, certificate_error, ssl_error = _load_api_with_aiohttp_doubles()

    class FailingSession:
        def __init__(self, error):
            self.error = error

        async def request(self, *_args, **_kwargs):
            raise self.error

    async def assert_tls_error(error):
        client = api.SurvNGApiClient(FailingSession(error), "https://survng.example")
        try:
            await client._response("GET", "/api/health")
        except api.SurvNGTLSError:
            return
        raise AssertionError("TLS connector failure was not classified as SurvNGTLSError")

    import asyncio

    asyncio.run(assert_tls_error(certificate_error()))
    asyncio.run(assert_tls_error(ssl_error()))


def test_incident_payload_does_not_publish_protected_snapshot_url() -> None:
    source = (ROOT / "custom_components" / "survng" / "event.py").read_text()
    tree = ast.parse(source)
    payload_keys = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "snapshot_url" not in payload_keys
