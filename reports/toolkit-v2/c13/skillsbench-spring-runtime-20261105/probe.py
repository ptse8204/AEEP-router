"""Verify the three offline runtime executables without running a task."""
import json
import os
import platform
import ssl
import subprocess
import sys

assert platform.machine() == 'x86_64'
assert tuple(sys.version_info[:3]) == (3, 12, 16)
java_home = '/root/.sdkman/candidates/java/21.0.2-tem'
maven_home = '/root/.sdkman/candidates/maven/3.9.6'
env = {'HOME': '/tmp', 'PATH': java_home+'/bin:/usr/bin:/bin', 'JAVA_HOME': java_home,
       'MAVEN_OPTS': '-Xmx256m -XX:ActiveProcessorCount=1', 'LC_ALL': 'C'}

def version(*args):
    result = subprocess.run(args, env=env, cwd='/tmp', capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    return result.stdout + result.stderr

assert '21.0.2' in version(java_home+'/bin/java', '-version')
maven = version(maven_home+'/bin/mvn', '--offline', '--version')
assert 'Apache Maven 3.9.6' in maven and '21.0.2' in maven
print(json.dumps({'python': platform.python_version(), 'architecture': platform.machine(),
                  'openssl': ssl.OPENSSL_VERSION, 'java': '21.0.2', 'maven': '3.9.6',
                  'maven_goal_run': False, 'reference_executed': False}))
