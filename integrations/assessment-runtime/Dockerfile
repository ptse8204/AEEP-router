FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0
RUN python3 -m pip install --no-cache-dir 'cryptography>=43,<47' 'httpx>=0.27,<1' 'jsonschema>=4.22,<5' 'opentelemetry-api>=1.25,<2' 'psutil>=5.9,<8' 'pydantic>=2.8,<3' 'PyYAML>=6,<7' 'rfc8785>=0.1.4,<0.2' 'typer>=0.12,<1' 'openpyxl==3.1.5'
USER 65534:65534
WORKDIR /tmp
