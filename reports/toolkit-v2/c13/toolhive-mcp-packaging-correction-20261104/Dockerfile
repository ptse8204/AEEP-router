FROM aeep-toolkit-v2/repository-grader:py313-shared-native-git-20261028
COPY server.py /opt/aeep-reviewed-mcp.py
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/aeep-reviewed-mcp.py"]
CMD []
